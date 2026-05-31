from __future__ import annotations

import json

from irbg.analysis.aggregate import aggregate_run_score
from irbg.analysis.compare import compare_runs
from irbg.db.operations import (
    DbConfig,
    connect,
    create_benchmark_run,
    upsert_model,
    upsert_pillar_score,
    upsert_run_manifest,
)
from irbg.db.schema import create_tables


def test_compare_runs(tmp_path) -> None:
    db_path = tmp_path / "compare.sqlite"
    conn = connect(DbConfig(path=db_path))
    create_tables(conn)

    upsert_model(
        conn,
        id="model_a",
        name="Model A",
        provider="openrouter",
        model_id="provider/model-a",
    )
    upsert_model(
        conn,
        id="model_b",
        name="Model B",
        provider="openrouter",
        model_id="provider/model-b",
    )

    run_a = create_benchmark_run(
        conn,
        model_id="model_a",
        mode="baseline",
        status="completed",
        config_snapshot="{}",
    )
    run_b = create_benchmark_run(
        conn,
        model_id="model_b",
        mode="baseline",
        status="completed",
        config_snapshot="{}",
    )

    upsert_pillar_score(
        conn,
        run_id=run_a,
        pillar="p1_demographic_consistency",
        score=85.0,
        breakdown_json="{}",
        notes="a",
    )
    upsert_pillar_score(
        conn,
        run_id=run_b,
        pillar="p1_demographic_consistency",
        score=75.0,
        breakdown_json="{}",
        notes="b",
    )
    conn.close()

    aggregate_run_score(db_path=db_path, run_id=run_a)
    aggregate_run_score(db_path=db_path, run_id=run_b)

    result = compare_runs(
        db_path=db_path,
        left_run_id=run_a,
        right_run_id=run_b,
    )

    assert result.left_score == 85.0
    assert result.right_score == 75.0
    assert result.score_delta == 10.0


def _breakdown(scenarios: dict[str, float]) -> str:
    return json.dumps(
        {
            "scenarios": [
                {"scenario_id": sid, "score": score}
                for sid, score in scenarios.items()
            ]
        }
    )


def test_compare_per_scenario_regression(tmp_path) -> None:
    db_path = tmp_path / "regress.sqlite"
    conn = connect(DbConfig(path=db_path))
    create_tables(conn)

    for mid in ("model_old", "model_new"):
        upsert_model(
            conn,
            id=mid,
            name=mid,
            provider="openrouter",
            model_id=f"provider/{mid}",
        )

    pillar = "p2_procedural_integrity"
    left = create_benchmark_run(
        conn, model_id="model_old", mode="baseline", status="completed"
    )
    right = create_benchmark_run(
        conn, model_id="model_new", mode="baseline", status="completed"
    )

    # S1: pass -> fail (newly_failing); S2: unchanged; S3: improved;
    # S4: fail -> worse fail (regressed).
    upsert_pillar_score(
        conn,
        run_id=left,
        pillar=pillar,
        score=65.0,
        breakdown_json=_breakdown(
            {"S1": 90.0, "S2": 80.0, "S3": 40.0, "S4": 50.0}
        ),
        notes="old",
    )
    upsert_pillar_score(
        conn,
        run_id=right,
        pillar=pillar,
        score=57.5,
        breakdown_json=_breakdown(
            {"S1": 50.0, "S2": 80.0, "S3": 60.0, "S4": 40.0}
        ),
        notes="new",
    )

    # Identical scenario-set hash => apples-to-apples comparison.
    for rid in (left, right):
        upsert_run_manifest(
            conn,
            run_id=rid,
            model_alias="m",
            model_snapshot_json="{}",
            scenario_set_version="v1",
            scenario_set_hash="deadbeefdeadbeef",
            seed=None,
            timestamp="2026-01-01T00:00:00Z",
        )
    conn.close()

    aggregate_run_score(db_path=db_path, run_id=left)
    aggregate_run_score(db_path=db_path, run_id=right)

    result = compare_runs(db_path=db_path, left_run_id=left, right_run_id=right)

    assert result.scenario_set_match is True
    assert result.summary == {
        "newly_failing": 1,
        "unchanged": 1,
        "improved": 1,
        "regressed": 1,
    }
    assert result.regressed_scenarios == ["S1", "S4"]

    by_id = {d.scenario_id: d for d in result.scenario_deltas}
    assert by_id["S1"].classification == "newly_failing"
    assert by_id["S2"].classification == "unchanged"
    assert by_id["S3"].classification == "improved"
    assert by_id["S4"].classification == "regressed"
    assert by_id["S3"].delta == 20.0


def test_compare_flags_scenario_set_mismatch(tmp_path) -> None:
    db_path = tmp_path / "mismatch.sqlite"
    conn = connect(DbConfig(path=db_path))
    create_tables(conn)

    for mid in ("model_a", "model_b"):
        upsert_model(
            conn,
            id=mid,
            name=mid,
            provider="openrouter",
            model_id=f"provider/{mid}",
        )

    pillar = "p2_procedural_integrity"
    left = create_benchmark_run(
        conn, model_id="model_a", mode="baseline", status="completed"
    )
    right = create_benchmark_run(
        conn, model_id="model_b", mode="baseline", status="completed"
    )
    upsert_pillar_score(
        conn,
        run_id=left,
        pillar=pillar,
        score=90.0,
        breakdown_json=_breakdown({"S1": 90.0}),
        notes="a",
    )
    upsert_pillar_score(
        conn,
        run_id=right,
        pillar=pillar,
        score=90.0,
        breakdown_json=_breakdown({"S1": 90.0}),
        notes="b",
    )
    upsert_run_manifest(
        conn,
        run_id=left,
        model_alias="a",
        model_snapshot_json="{}",
        scenario_set_version="v1",
        scenario_set_hash="aaaa",
        seed=None,
        timestamp="t",
    )
    upsert_run_manifest(
        conn,
        run_id=right,
        model_alias="b",
        model_snapshot_json="{}",
        scenario_set_version="v2",
        scenario_set_hash="bbbb",
        seed=None,
        timestamp="t",
    )
    conn.close()

    aggregate_run_score(db_path=db_path, run_id=left)
    aggregate_run_score(db_path=db_path, run_id=right)

    result = compare_runs(db_path=db_path, left_run_id=left, right_run_id=right)
    assert result.scenario_set_match is False
    assert result.left_scenario_set_hash == "aaaa"
    assert result.right_scenario_set_hash == "bbbb"


def test_compare_includes_p1_total_score(tmp_path) -> None:
    db_path = tmp_path / "p1diff.sqlite"
    conn = connect(DbConfig(path=db_path))
    create_tables(conn)

    for mid in ("old", "new"):
        upsert_model(
            conn,
            id=mid,
            name=mid,
            provider="openrouter",
            model_id=f"provider/{mid}",
        )

    pillar = "p1_demographic_consistency"

    def _p1(total: float) -> str:
        return json.dumps(
            {"scenarios": [{"scenario_id": "P1-A", "total_score": total}]}
        )

    left = create_benchmark_run(
        conn, model_id="old", mode="baseline", status="completed"
    )
    right = create_benchmark_run(
        conn, model_id="new", mode="baseline", status="completed"
    )
    upsert_pillar_score(
        conn,
        run_id=left,
        pillar=pillar,
        score=90.0,
        breakdown_json=_p1(90.0),
        notes="old",
    )
    upsert_pillar_score(
        conn,
        run_id=right,
        pillar=pillar,
        score=60.0,
        breakdown_json=_p1(60.0),
        notes="new",
    )
    conn.close()

    aggregate_run_score(db_path=db_path, run_id=left)
    aggregate_run_score(db_path=db_path, run_id=right)

    result = compare_runs(db_path=db_path, left_run_id=left, right_run_id=right)

    by_id = {d.scenario_id: d for d in result.scenario_deltas}
    assert "P1-A" in by_id
    assert by_id["P1-A"].pillar == pillar
    assert by_id["P1-A"].classification == "newly_failing"
    assert "P1-A" in result.regressed_scenarios
