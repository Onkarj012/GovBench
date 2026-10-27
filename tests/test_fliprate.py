from __future__ import annotations

import math
import sqlite3
from pathlib import Path

import pytest

from irbg.analysis.fliprate import (
    DECISION_PATTERNS,
    FlipRateError,
    compute_flip_rate,
    compute_flip_rate_for_run,
    extract_decision,
    pair_responses,
)
from irbg.db.operations import (
    DbConfig,
    connect,
    create_benchmark_run,
    insert_response,
    upsert_model,
    upsert_scenario_record,
)
from irbg.db.schema import create_tables

# ---------------------------------------------------------------------------
# Decision extraction
# ---------------------------------------------------------------------------


def test_extract_decision_grant() -> None:
    assert extract_decision("I recommend granting the permit.") == "grant"
    assert extract_decision("The application is approved.") == "grant"
    assert extract_decision("Release the defendant.") == "grant"


def test_extract_decision_deny() -> None:
    assert extract_decision("I deny the request.") == "deny"
    assert extract_decision("The claim must be rejected.") == "deny"
    assert extract_decision("Do not grant the licence.") == "deny"


def test_extract_decision_escalate() -> None:
    assert extract_decision("This should be escalated.") == "escalate"
    assert extract_decision("I refer this to a supervisor.") == "escalate"
    assert extract_decision("We need further review.") == "escalate"


def test_extract_decision_abstain() -> None:
    assert extract_decision("I abstain pending more information.") == "abstain"
    assert (
        extract_decision("Insufficient information to determine.") == "abstain"
    )
    assert extract_decision("We cannot decide without more data.") == "abstain"


def test_extract_decision_ambiguous_returns_none() -> None:
    assert extract_decision("Grant the request, but also deny it.") is None
    assert extract_decision("") is None
    assert extract_decision(None) is None
    assert extract_decision("The weather is nice today.") is None


def test_decision_patterns_is_auditable_table() -> None:
    decisions = {group[0] for group in DECISION_PATTERNS}
    assert decisions == {"grant", "deny", "escalate", "abstain"}


# ---------------------------------------------------------------------------
# Flip-rate computation
# ---------------------------------------------------------------------------


def test_compute_flip_rate_no_pairs() -> None:
    result = compute_flip_rate([])
    assert result.n_pairs == 0
    assert result.n_decided == 0
    assert result.n_flips == 0
    assert result.flip_rate == 0.0


def test_compute_flip_rate_all_flips() -> None:
    pairs = [
        ("Grant the permit.", "Deny the permit."),
        ("Approve.", "Reject."),
    ]
    result = compute_flip_rate(pairs)
    assert result.n_pairs == 2
    assert result.n_decided == 2
    assert result.n_flips == 2
    assert result.flip_rate == 1.0


def test_compute_flip_rate_undecided_excluded() -> None:
    pairs = [
        ("Grant.", "The weather is nice."),
        ("Deny.", "Approve."),
    ]
    result = compute_flip_rate(pairs)
    assert result.n_pairs == 2
    assert result.n_decided == 1
    assert result.n_flips == 1
    assert result.flip_rate == 1.0


def test_compute_flip_rate_no_flip() -> None:
    pairs = [
        ("Grant.", "Approve."),
        ("Deny.", "Reject."),
    ]
    result = compute_flip_rate(pairs)
    assert result.n_flips == 0
    assert result.flip_rate == 0.0


def test_compute_flip_rate_wilson_ci_hand_computed() -> None:
    """100 pairs, 25 flips -> Wilson 95% CI approx [0.173, 0.342]."""
    pairs = [("Grant.", "Deny.")] * 25 + [("Grant.", "Approve.")] * 75
    result = compute_flip_rate(pairs)
    assert result.n_pairs == 100
    assert result.n_decided == 100
    assert result.n_flips == 25
    assert result.flip_rate == 0.25
    assert 0.17 <= result.ci_low <= 0.18
    assert 0.34 <= result.ci_high <= 0.35


# ---------------------------------------------------------------------------
# Pairing and DB integration
# ---------------------------------------------------------------------------


def _make_row(
    scenario_id: str,
    variant_id: str,
    instance_json: str | None,
    raw_response: str | None,
    pillar: str = "p1_demographic_consistency",
) -> sqlite3.Row:
    """Build a sqlite3.Row-like object for pairing tests."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE t (scenario_id, variant_id, instance_json, "
        "raw_response, pillar)"
    )
    conn.execute(
        "INSERT INTO t VALUES (?, ?, ?, ?, ?)",
        (scenario_id, variant_id, instance_json, raw_response, pillar),
    )
    row = conn.execute("SELECT * FROM t").fetchone()
    conn.close()
    return row


def test_pair_responses_groups_by_instance_json() -> None:
    rows = [
        _make_row("S1", "inst0/varA", '{"x":1}', "Grant."),
        _make_row("S1", "inst0/varB", '{"x":1}', "Deny."),
        _make_row("S1", "inst1/varA", '{"x":2}', "Grant."),
        _make_row("S1", "inst1/varB", '{"x":2}', "Grant."),
    ]
    pairs = pair_responses(rows)
    assert len(pairs) == 2


def test_pair_responses_ignores_single_variant_groups() -> None:
    rows = [
        _make_row("S1", "inst0/varA", '{"x":1}', "Grant."),
    ]
    pairs = pair_responses(rows)
    assert pairs == []


def test_compute_flip_rate_for_run_empty_raises(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite"
    conn = connect(DbConfig(path=db_path))
    try:
        create_tables(conn)
        upsert_model(conn, id="m", name="M", provider="p", model_id="mid")
        run_id = create_benchmark_run(
            conn, model_id="m", mode="baseline", status="running"
        )
    finally:
        conn.close()

    with pytest.raises(FlipRateError):
        compute_flip_rate_for_run(db_path=db_path, run_id=run_id)


def test_compute_flip_rate_for_run_with_pairs(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite"
    conn = connect(DbConfig(path=db_path))
    try:
        create_tables(conn)
        upsert_model(conn, id="m", name="M", provider="p", model_id="mid")
        upsert_scenario_record(
            conn,
            id="S1",
            pillar="p1_demographic_consistency",
            category="demo",
            jurisdiction=None,
            difficulty=None,
        )
        run_id = create_benchmark_run(
            conn, model_id="m", mode="baseline", status="running"
        )
        for variant_id, response in (
            ("inst0/varA", "Grant the application."),
            ("inst0/varB", "Deny the application."),
        ):
            insert_response(
                conn,
                run_id=run_id,
                scenario_id="S1",
                variant_id=variant_id,
                mode="baseline",
                turn_number=1,
                system_prompt_sent="System.",
                user_prompt_sent="User.",
                raw_response=response,
                latency_ms=0,
                instance_json='{"seed":0}',
                response_tokens=0,
            )
    finally:
        conn.close()

    report = compute_flip_rate_for_run(db_path=db_path, run_id=run_id)
    assert report.run_id == run_id
    assert len(report.pillars) == 1
    pillar, result = report.pillars[0]
    assert pillar == "p1_demographic_consistency"
    assert result.n_pairs == 1
    assert result.n_decided == 1
    assert result.n_flips == 1
    assert math.isclose(result.flip_rate, 1.0)
