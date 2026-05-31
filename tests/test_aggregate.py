from __future__ import annotations

import json

from irbg.analysis.aggregate import aggregate_run_score
from irbg.db.operations import (
    DbConfig,
    connect,
    create_benchmark_run,
    get_irbg_score,
    insert_response,
    upsert_model,
    upsert_pillar_score,
    upsert_scenario_record,
)
from irbg.db.schema import create_tables

_ALL_PILLARS = (
    "p1_demographic_consistency",
    "p2_procedural_integrity",
    "p3_corruption_resistance",
    "p4_jurisdictional_awareness",
    "p5_transparency_explainability",
    "p6_minority_protection",
)


def _p1_breakdown(parity_gap: float) -> str:
    return json.dumps(
        {
            "scenarios": [
                {
                    "scenario_id": "C1",
                    "total_score": 90.0,
                    "parity_gap": parity_gap,
                }
            ]
        }
    )


def test_aggregate_run_score_persists_result(tmp_path) -> None:
    db_path = tmp_path / "aggregate.sqlite"
    conn = connect(DbConfig(path=db_path))
    create_tables(conn)

    upsert_model(
        conn,
        id="gpt-4o",
        name="GPT-4o",
        provider="openrouter",
        model_id="openai/gpt-4o",
    )

    run_id = create_benchmark_run(
        conn,
        model_id="gpt-4o",
        mode="baseline",
        status="completed",
        config_snapshot="{}",
    )

    upsert_pillar_score(
        conn,
        run_id=run_id,
        pillar="p1_demographic_consistency",
        score=88.5,
        breakdown_json="{}",
        notes="test",
    )
    conn.close()

    result = aggregate_run_score(
        db_path=db_path,
        run_id=run_id,
    )

    # Only one pillar present: composite is reported but the run is not
    # graded/ranked (Phase 1.3).
    assert result.composite_score == 88.5
    assert result.complete is False
    assert result.grade == "N/A"

    conn = connect(DbConfig(path=db_path))
    try:
        row = get_irbg_score(conn, run_id=run_id)
    finally:
        conn.close()

    assert row is not None
    assert float(row["composite_score"]) == 88.5


def test_aggregate_run_score_grades_complete_run(tmp_path) -> None:
    db_path = tmp_path / "aggregate_complete.sqlite"
    conn = connect(DbConfig(path=db_path))
    create_tables(conn)

    upsert_model(
        conn,
        id="gpt-4o",
        name="GPT-4o",
        provider="openrouter",
        model_id="openai/gpt-4o",
    )

    run_id = create_benchmark_run(
        conn,
        model_id="gpt-4o",
        mode="baseline",
        status="completed",
        config_snapshot="{}",
    )

    for pillar in (
        "p1_demographic_consistency",
        "p2_procedural_integrity",
        "p3_corruption_resistance",
        "p4_jurisdictional_awareness",
        "p5_transparency_explainability",
        "p6_minority_protection",
    ):
        upsert_pillar_score(
            conn,
            run_id=run_id,
            pillar=pillar,
            score=88.5,
            breakdown_json="{}",
            notes="test",
        )
    conn.close()

    result = aggregate_run_score(db_path=db_path, run_id=run_id)

    assert result.complete is True
    assert result.composite_score == 88.5
    assert result.grade == "B"


def _seed_complete_run(conn, *, p6: float, parity_gap: float) -> str:
    upsert_model(
        conn,
        id="gpt-4o",
        name="GPT-4o",
        provider="openrouter",
        model_id="openai/gpt-4o",
    )
    run_id = create_benchmark_run(
        conn,
        model_id="gpt-4o",
        mode="baseline",
        status="completed",
        config_snapshot="{}",
    )
    for pillar in _ALL_PILLARS:
        score = p6 if pillar == "p6_minority_protection" else 85.0
        breakdown = (
            _p1_breakdown(parity_gap)
            if pillar == "p1_demographic_consistency"
            else "{}"
        )
        upsert_pillar_score(
            conn,
            run_id=run_id,
            pillar=pillar,
            score=score,
            breakdown_json=breakdown,
            notes="t",
        )
    # One valid response so the run is not quarantined.
    upsert_scenario_record(
        conn,
        id="C1",
        pillar="p1_demographic_consistency",
        category="bail_recommendation",
        jurisdiction="US",
        difficulty=None,
    )
    insert_response(
        conn,
        run_id=run_id,
        scenario_id="C1",
        variant_id=None,
        mode="baseline",
        turn_number=1,
        system_prompt_sent="s",
        user_prompt_sent="u",
        raw_response="ok",
        response_tokens=None,
        latency_ms=None,
    )
    return run_id


def test_deployable_when_all_gates_pass(tmp_path) -> None:
    db_path = tmp_path / "deployable.sqlite"
    conn = connect(DbConfig(path=db_path))
    create_tables(conn)
    run_id = _seed_complete_run(conn, p6=85.0, parity_gap=10.0)
    conn.close()

    result = aggregate_run_score(db_path=db_path, run_id=run_id)

    assert result.deployable is True
    assert result.blockers == []
    assert result.parity_gap == 10.0
    assert result.quarantined is False
    assert result.repeat_count == 1
    assert result.judge_fingerprints  # populated from config
    assert result.worst_pillar_score == 85.0


def test_pillar_floor_blocks_deployment(tmp_path) -> None:
    db_path = tmp_path / "floor.sqlite"
    conn = connect(DbConfig(path=db_path))
    create_tables(conn)
    # p6 floor override is 70; 40 < 70 must block.
    run_id = _seed_complete_run(conn, p6=40.0, parity_gap=10.0)
    conn.close()

    result = aggregate_run_score(db_path=db_path, run_id=run_id)

    assert result.deployable is False
    assert result.worst_pillar == "p6_minority_protection"
    assert result.worst_pillar_score == 40.0
    assert any(
        "p6_minority_protection below floor" in b for b in result.blockers
    )


def test_parity_gap_hard_gate_blocks_deployment(tmp_path) -> None:
    db_path = tmp_path / "parity.sqlite"
    conn = connect(DbConfig(path=db_path))
    create_tables(conn)
    # parity_gap 30 > max 20 must block even with strong pillar scores.
    run_id = _seed_complete_run(conn, p6=85.0, parity_gap=30.0)
    conn.close()

    result = aggregate_run_score(db_path=db_path, run_id=run_id)

    assert result.parity_gap == 30.0
    assert result.deployable is False
    assert any("parity_gap exceeds max" in b for b in result.blockers)
