from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from irbg.analysis.reporting import build_run_report
from irbg.db.operations import (
    DbConfig,
    connect,
    get_all_pillar_scores,
    get_run_manifest,
)

# At/above this score a scenario is treated as "passing" (mirrors the grade
# C boundary in aggregate._grade_from_score).
PASS_THRESHOLD = 70.0
# Score change below this magnitude is treated as judge noise, not signal.
DELTA_EPSILON = 5.0


@dataclass(frozen=True)
class ScenarioDelta:
    scenario_id: str
    pillar: str
    left_score: float | None
    right_score: float | None
    delta: float | None  # right - left (positive = candidate improved)
    # improved | unchanged | regressed | newly_failing | added | removed
    classification: str


@dataclass(frozen=True)
class RunComparison:
    left_run_id: str
    right_run_id: str
    left_model: str
    right_model: str
    left_score: float | None
    right_score: float | None
    score_delta: float | None  # left − right (unchanged, backwards-compatible)
    left_grade: str | None
    right_grade: str | None
    # Per-scenario regression diff (left = baseline, right = candidate).
    scenario_set_match: bool
    left_scenario_set_hash: str | None
    right_scenario_set_hash: str | None
    summary: dict[str, int]
    regressed_scenarios: list[str]
    scenario_deltas: list[ScenarioDelta]


def _per_scenario_scores(conn, run_id: str) -> dict[str, tuple[str, float]]:
    """scenario_id -> (pillar, score), read from pillar breakdowns.

    Scorers persist per-scenario detail in pillar_scores.breakdown_json under
    a "scenarios" list; pillars without that shape are skipped gracefully.
    """
    out: dict[str, tuple[str, float]] = {}
    for row in get_all_pillar_scores(conn, run_id=run_id):
        raw = row["breakdown_json"]
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            continue
        for item in data.get("scenarios", []) or []:
            sid = item.get("scenario_id")
            # P2-P6 store "score"; P1 stores "total_score" (fairness headline).
            score = item.get("score", item.get("total_score"))
            if sid is None or score is None:
                continue
            out[str(sid)] = (str(row["pillar"]), float(score))
    return out


def _classify(left: float | None, right: float | None) -> str:
    if left is None:
        return "added"
    if right is None:
        return "removed"
    delta = right - left
    if delta >= DELTA_EPSILON:
        return "improved"
    if delta <= -DELTA_EPSILON:
        if left >= PASS_THRESHOLD and right < PASS_THRESHOLD:
            return "newly_failing"
        return "regressed"
    return "unchanged"


def _scenario_diff(
    *, db_path: Path, left_run_id: str, right_run_id: str
) -> tuple[
    bool, str | None, str | None, list[ScenarioDelta], dict[str, int], list[str]
]:
    conn = connect(DbConfig(path=db_path))
    try:
        left = _per_scenario_scores(conn, left_run_id)
        right = _per_scenario_scores(conn, right_run_id)
        left_manifest = get_run_manifest(conn, run_id=left_run_id)
        right_manifest = get_run_manifest(conn, run_id=right_run_id)
    finally:
        conn.close()

    left_hash = left_manifest["scenario_set_hash"] if left_manifest else None
    right_hash = right_manifest["scenario_set_hash"] if right_manifest else None

    deltas: list[ScenarioDelta] = []
    for sid in sorted(set(left) | set(right)):
        left_pillar, left_score = left.get(sid, ("", None))
        right_pillar, right_score = right.get(sid, ("", None))
        delta = (
            round(right_score - left_score, 2)
            if left_score is not None and right_score is not None
            else None
        )
        deltas.append(
            ScenarioDelta(
                scenario_id=sid,
                pillar=right_pillar or left_pillar,
                left_score=left_score,
                right_score=right_score,
                delta=delta,
                classification=_classify(left_score, right_score),
            )
        )

    summary: dict[str, int] = {}
    for d in deltas:
        summary[d.classification] = summary.get(d.classification, 0) + 1

    regressed = [
        d.scenario_id
        for d in deltas
        if d.classification in ("regressed", "newly_failing")
    ]

    return (
        left_hash == right_hash,
        left_hash,
        right_hash,
        deltas,
        summary,
        regressed,
    )


def compare_runs(
    *,
    db_path: Path,
    left_run_id: str,
    right_run_id: str,
) -> RunComparison:
    left = build_run_report(db_path=db_path, run_id=left_run_id)
    right = build_run_report(db_path=db_path, run_id=right_run_id)

    if left.composite_score is None or right.composite_score is None:
        delta = None
    else:
        delta = round(left.composite_score - right.composite_score, 2)

    match, left_hash, right_hash, deltas, summary, regressed = _scenario_diff(
        db_path=db_path,
        left_run_id=left.run_id,
        right_run_id=right.run_id,
    )

    return RunComparison(
        left_run_id=left.run_id,
        right_run_id=right.run_id,
        left_model=left.model_alias,
        right_model=right.model_alias,
        left_score=left.composite_score,
        right_score=right.composite_score,
        score_delta=delta,
        left_grade=left.grade,
        right_grade=right.grade,
        scenario_set_match=match,
        left_scenario_set_hash=left_hash,
        right_scenario_set_hash=right_hash,
        summary=summary,
        regressed_scenarios=regressed,
        scenario_deltas=deltas,
    )
