from __future__ import annotations

from irbg.analysis.aggregate import aggregate_run_score
from irbg.db.operations import (
    DbConfig,
    connect,
    create_benchmark_run,
    get_irbg_score,
    upsert_model,
    upsert_pillar_score,
)
from irbg.db.schema import create_tables


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
