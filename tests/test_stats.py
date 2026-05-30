from __future__ import annotations

from irbg.analysis.stats import _bootstrap_ci, compute_robustness_delta
from irbg.db.operations import (
    DbConfig,
    connect,
    create_benchmark_run,
    upsert_model,
    upsert_pillar_score,
)
from irbg.db.schema import create_tables


def test_bootstrap_ci_single_value() -> None:
    lo, hi = _bootstrap_ci([75.0])
    assert lo == hi == 75.0


def test_bootstrap_ci_range() -> None:
    values = [60.0, 70.0, 80.0, 90.0, 100.0]
    lo, hi = _bootstrap_ci(values)
    assert lo < hi
    assert 60.0 <= lo <= 100.0
    assert 60.0 <= hi <= 100.0


def test_robustness_delta(tmp_path) -> None:
    db_path = tmp_path / "stats.sqlite"
    conn = connect(DbConfig(path=db_path))
    create_tables(conn)

    upsert_model(conn, id="m1", name="M1", provider="x", model_id="x/m1")

    for mode, score in [("baseline", 80.0), ("pressure", 60.0)]:
        run_id = create_benchmark_run(
            conn,
            model_id="m1",
            mode=mode,
            status="completed",
            config_snapshot="{}",
        )
        upsert_pillar_score(
            conn,
            run_id=run_id,
            pillar="p1_demographic_consistency",
            score=score,
            breakdown_json="{}",
            notes="",
        )
    conn.close()

    report = compute_robustness_delta(
        db_path=db_path, model_alias="m1", mode="pressure"
    )
    assert report.pillars[0].delta == 20.0
    assert report.composite_delta == 20.0
