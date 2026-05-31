from __future__ import annotations

from pathlib import Path

from irbg.analysis.quality import assess_run_quality
from irbg.db.operations import (
    DbConfig,
    connect,
    create_benchmark_run,
    insert_response,
    upsert_model,
    upsert_scenario_record,
)
from irbg.db.schema import create_tables


def test_assess_run_quality_quarantines_mostly_empty(tmp_path: Path) -> None:
    db_path = tmp_path / "q.sqlite"
    conn = connect(DbConfig(path=db_path))
    create_tables(conn)

    upsert_model(
        conn,
        id="glm-4.7-flash",
        name="GLM",
        provider="openrouter",
        model_id="z-ai/glm-4.7-flash",
    )
    upsert_scenario_record(
        conn,
        id="P2-US-PROC-001",
        pillar="p2_procedural_integrity",
        category="procedure",
        jurisdiction="US",
        difficulty="hard",
    )
    run_id = create_benchmark_run(
        conn,
        model_id="glm-4.7-flash",
        mode="baseline",
        status="completed",
        config_snapshot="{}",
    )

    # 1 valid + 4 invalid (empty / legacy "None") -> 80% invalid.
    responses = ["A real legal analysis.", "", "None", "  ", "None"]
    for i, text in enumerate(responses):
        insert_response(
            conn,
            run_id=run_id,
            scenario_id="P2-US-PROC-001",
            variant_id=f"v{i}",
            mode="baseline",
            turn_number=1,
            system_prompt_sent="sys",
            user_prompt_sent="user",
            raw_response=text,
            response_tokens=1,
            latency_ms=10,
        )
    conn.close()

    quality = assess_run_quality(db_path=db_path, run_id=run_id)

    assert quality.total == 5
    assert quality.invalid == 4
    assert quality.invalid_ratio == 0.8
    assert quality.quarantined is True
