from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

from irbg.analysis.aggregate import _grade_from_score
from irbg.analysis.quality import DEFAULT_INVALID_THRESHOLD, assess_all_runs
from irbg.analysis.stats import _bootstrap_ci
from irbg.config import get_model_config
from irbg.db.operations import (
    DbConfig,
    connect,
    get_all_pillar_scores,
    get_responses_for_run,
    list_benchmark_runs,
)

# OpenRouter provider prefix (ModelConfig.family) -> frontend family key.
_FAMILY_MAP = {"moonshotai": "moonshot", "z-ai": "zhipu"}

# 6 pillars x 3 modes; matches the frontend coverageRatio denominator.
_COVERAGE_DENOMINATOR = 18


class ExportError(Exception):
    """Raised when the leaderboard cannot be exported."""


def _avg(values: list[float]) -> float:
    return round(mean(values), 2) if values else 0.0


def _run_result(run_row, pillar_row, resp_rows) -> dict:
    pillar = str(pillar_row["pillar"])
    score = round(float(pillar_row["score"]), 2)
    latencies = [
        int(r["latency_ms"]) for r in resp_rows if r["latency_ms"] is not None
    ]
    tokens = [
        int(r["response_tokens"])
        for r in resp_rows
        if r["response_tokens"] is not None
    ]
    result = {
        "run_id": str(run_row["id"])[:8],
        "mode": str(run_row["mode"]),
        "pillar": pillar,
        "score": score,
        "grade": _grade_from_score(score),
        "avg_latency_ms": _avg(latencies),
        "avg_tokens": _avg(tokens),
    }
    if pillar == "p1_demographic_consistency":
        result["parity_gap"] = round(100.0 - score, 2)
    breakdown = json.loads(pillar_row["breakdown_json"] or "{}")
    scenarios = breakdown.get("scenarios", [])
    if any(
        "judge_disagreement" in (s.get("judge_flags") or []) for s in scenarios
    ):
        result["judge_disagreement"] = True
    return result


def _model_data(alias: str, runs: list[dict]) -> dict:
    cfg = get_model_config(alias)
    by_pillar: dict[str, list[float]] = defaultdict(list)
    by_pillar_mode: dict[tuple[str, str], list[float]] = defaultdict(list)
    for run in runs:
        by_pillar[run["pillar"]].append(run["score"])
        by_pillar_mode[(run["pillar"], run["mode"])].append(run["score"])

    pillar_ci = []
    for pillar in sorted(by_pillar):
        scores = by_pillar[pillar]
        lo, hi = _bootstrap_ci(scores)
        pillar_ci.append(
            {
                "pillar": pillar,
                "mean": _avg(scores),
                "ci_low": lo,
                "ci_high": hi,
                "n": len(scores),
            }
        )

    robustness = []
    for pillar in sorted(by_pillar):
        base = by_pillar_mode.get((pillar, "baseline"))
        pressure = by_pillar_mode.get((pillar, "pressure"))
        if base and pressure:
            b, p = _avg(base), _avg(pressure)
            robustness.append(
                {
                    "pillar": pillar,
                    "baseline": b,
                    "pressure": p,
                    "delta": round(b - p, 2),
                }
            )

    return {
        "alias": alias,
        "displayName": cfg.name,
        "family": _FAMILY_MAP.get(cfg.family, cfg.family),
        "coverageRatio": round(len(runs) / _COVERAGE_DENOMINATOR, 4),
        "pillarCI": pillar_ci,
        "robustness": robustness,
        "runs": sorted(runs, key=lambda r: (r["mode"], r["pillar"])),
    }


def build_leaderboard(
    *,
    db_path: Path,
    threshold: float = DEFAULT_INVALID_THRESHOLD,
) -> list[dict]:
    """Build the leaderboard dataset from the DB, excluding quarantined runs."""
    quarantined = {
        q.run_id
        for q in assess_all_runs(db_path=db_path, threshold=threshold)
        if q.quarantined
    }

    conn = connect(DbConfig(path=db_path))
    try:
        runs_by_model: dict[str, list[dict]] = defaultdict(list)
        for run_row in list_benchmark_runs(conn):
            run_id = str(run_row["id"])
            if run_id in quarantined:
                continue
            pillar_rows = get_all_pillar_scores(conn, run_id=run_id)
            if not pillar_rows:
                continue
            resp_rows = get_responses_for_run(conn, run_id=run_id)
            for pillar_row in pillar_rows:
                runs_by_model[str(run_row["model_id"])].append(
                    _run_result(run_row, pillar_row, resp_rows)
                )
    finally:
        conn.close()

    return [
        _model_data(alias, runs)
        for alias, runs in sorted(runs_by_model.items())
    ]


def write_leaderboard(
    *,
    db_path: Path,
    output_path: Path,
    threshold: float = DEFAULT_INVALID_THRESHOLD,
) -> int:
    """Write the leaderboard JSON; returns the number of models exported."""
    models = build_leaderboard(db_path=db_path, threshold=threshold)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(models, indent=2) + "\n")
    return len(models)
