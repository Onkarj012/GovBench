from __future__ import annotations

from irbg.db.operations import (
    DbConfig,
    connect,
    create_benchmark_run,
    insert_response,
    upsert_model,
    upsert_scenario_record,
)
from irbg.db.schema import create_tables
from irbg.scoring import judge
from irbg.scoring.judge import JudgeVerdict
from irbg.scoring.p2 import score_p2_run


def _fake_judge(*, pillar, scenario_context, response_text, **_):
    # Score == the numeric text, so repeats can carry distinct scores.
    return JudgeVerdict(
        score=float(response_text or 0),
        reasoning="ok",
        flags=[],
        raw_response="",
    )


def test_repeats_collapse_to_median_and_ci(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(judge, "judge_response", _fake_judge)

    db_path = tmp_path / "repeats.sqlite"
    conn = connect(DbConfig(path=db_path))
    create_tables(conn)

    upsert_model(
        conn,
        id="m",
        name="m",
        provider="openrouter",
        model_id="provider/m",
    )
    run_id = create_benchmark_run(
        conn, model_id="m", mode="baseline", status="completed"
    )
    upsert_scenario_record(
        conn,
        id="S1",
        pillar="p2_procedural_integrity",
        category="x",
        jurisdiction="US",
        difficulty=None,
    )
    for idx, score_text in enumerate(("70", "90")):
        insert_response(
            conn,
            run_id=run_id,
            scenario_id="S1",
            variant_id=None,
            mode="baseline",
            turn_number=1,
            repeat_index=idx,
            system_prompt_sent="s",
            user_prompt_sent="u",
            raw_response=score_text,
            response_tokens=None,
            latency_ms=None,
        )
    conn.close()

    result = score_p2_run(db_path=db_path, run_id=run_id)

    # Two repeats of one scenario collapse to a single entry.
    assert result.scenario_count == 1
    item = result.scenarios[0]
    assert item.repeat_n == 2
    assert item.score == 80.0  # median of 70 and 90
    assert item.score_ci_low <= 80.0 <= item.score_ci_high
    assert result.overall_score == 80.0
