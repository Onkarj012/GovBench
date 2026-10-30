from __future__ import annotations

from pathlib import Path

from irbg.db.operations import DbConfig, connect, insert_element_verdict
from irbg.db.schema import create_tables
from irbg.scenarios.template_loader import load_scenario_template
from irbg.scoring.rubric import Rubric, RubricElement, score_against_rubric

ROOT = Path(__file__).resolve().parents[1]


def test_new_p3_scenarios_define_pressure_overlay() -> None:
    """New procedural P3 scenarios must support the pressure suite."""
    names = (
        "p3_insufficient_info_us_001.json",
        "p3_false_authority_trap_eu_001.json",
    )
    for name in names:
        template = load_scenario_template(
            ROOT / "scenarios/v1/p3_corruption" / name
        )
        assert "pressure" in template.modes


def test_rejected_forbidden_hint_requires_semantic_verification() -> None:
    """A forbidden substring inside a negated word is not a verdict."""
    rubric = Rubric(
        answer_key=None,
        elements=[
            RubricElement("required", 1, "valid ruling", [], "required"),
            RubricElement(
                "forbidden",
                1,
                "admissible evidence",
                ["admissible"],
                "forbidden",
            ),
        ],
        expects_insufficient_info=False,
    )
    seen: list[str] = []

    def verify(element, _text: str) -> tuple[bool, str]:  # type: ignore[no-untyped-def]
        seen.append(element.id)
        return element.id == "required", "judge"

    score_against_rubric(
        rubric,
        "The evidence is inadmissible.",
        verify_element=verify,
    )
    assert "forbidden" in seen


def test_fake_case_trap_means_reliance_not_spotting() -> None:
    """Trap metadata must describe the harmful model behavior."""
    template = load_scenario_template(
        ROOT / "scenarios/v1/p3_corruption/p3_false_authority_trap_eu_001.json"
    )
    trap = next(
        item for item in template.rubric["traps"] if item["id"] == "fake_case"
    )
    assert "reli" in trap["desc"].lower() or "treat" in trap["desc"].lower()


def test_cached_vote_reasoning_is_readable_from_sqlite_row() -> None:
    """Cached vote evidence must use sqlite row indexing."""
    conn = connect(DbConfig(path=Path(":memory:")))
    try:
        row = conn.execute("SELECT 'reasoning' AS reasoning").fetchone()
        assert row["reasoning"] == "reasoning"
        # sqlite3.Row intentionally has no dict.get method.
        assert not hasattr(row, "get")
    finally:
        conn.close()


def test_p3_fact_space_generates_without_explicit_seed() -> None:
    """Fact spaces should be sampled when callers omit a seed."""
    source = (ROOT / "src/irbg/engine/runner.py").read_text()
    assert "template.fact_space is not None and seed is not None" not in source


def test_adversarial_turn_records_keep_instance_facts() -> None:
    """Each adversarial turn must retain its sampled instance identity."""
    source = (ROOT / "src/irbg/engine/runner.py").read_text()
    adversarial = source[
        source.index("def _run_adversarial") : source.index(
            "def _execute_adversarial_sequence"
        )
    ]
    assert "instance_json=None" not in adversarial


def test_flip_rate_counts_independent_instance_groups() -> None:
    """Overlapping variant pairs must not inflate the CI sample size."""
    from irbg.analysis.fliprate import compute_flip_rate

    result = compute_flip_rate(
        [("grant", "grant")] * 56,
        groups=["one"] * 28 + ["two"] * 28,
    )
    assert result.flip_rate == 0
    assert result.ci_high > 0.5


def test_response_verdict_upsert_replaces_prior_vote(tmp_path: Path) -> None:
    """A response's re-score replaces its prior element verdict."""
    conn = connect(DbConfig(path=tmp_path / "verdicts.sqlite"))
    try:
        create_tables(conn)
        for present, evidence in ((False, "first"), (True, "updated")):
            insert_element_verdict(
                conn,
                run_id="run",
                scenario_id="scenario",
                response_id="response",
                element_id="fake_case",
                present=present,
                evidence=evidence,
                created_at="2026-01-01T00:00:00+00:00",
            )

        rows = conn.execute(
            "SELECT response_id, element_id, present, evidence "
            "FROM element_verdicts"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["response_id"] == "response"
        assert rows[0]["present"] == 1
        assert rows[0]["evidence"] == "updated"
    finally:
        conn.close()
