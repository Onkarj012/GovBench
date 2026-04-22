from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean

from irbg.db.operations import (
    DbConfig,
    connect,
    get_responses_for_run,
    get_run,
    upsert_pillar_score,
)


@dataclass(frozen=True)
class P2ScenarioScore:
    scenario_id: str
    category: str
    issue_detected: bool
    score: float


@dataclass(frozen=True)
class P2RunScore:
    run_id: str
    model_alias: str
    mode: str
    scenario_count: int
    overall_score: float
    scenarios: list[P2ScenarioScore]


class P2ScoringError(Exception):
    """Raised when a P2 run cannot be scored."""


def score_p2_run(
    *,
    db_path: Path,
    run_id: str,
) -> P2RunScore:
    """Score a P2 (Procedural Integrity) run.

    MVP implementation - checks if model identifies procedural issues
    (illegal evidence, premature verdict, wrong jurisdiction).
    """
    conn = connect(DbConfig(path=db_path))

    try:
        run_row = get_run(conn, run_id=run_id)
        if run_row is None:
            raise P2ScoringError(f"Run not found: {run_id}")

        rows = get_responses_for_run(conn, run_id=run_id)
        p2_rows = [
            row for row in rows if row["pillar"] == "p2_procedural_integrity"
        ]

        if not p2_rows:
            raise P2ScoringError(
                f"Run '{run_id}' contains no P2 procedural responses."
            )

        scenario_scores: list[P2ScenarioScore] = []

        for row in p2_rows:
            scenario_id = str(row["scenario_id"])
            category = str(row["category"])
            text = (row["raw_response"] or "").strip().lower()

            # MVP: Check if procedural issue is detected
            issue_detected = _detect_procedural_issue(category, text)
            score = 100.0 if issue_detected else 0.0

            scenario_scores.append(
                P2ScenarioScore(
                    scenario_id=scenario_id,
                    category=category,
                    issue_detected=issue_detected,
                    score=score,
                )
            )

        overall_score = round(
            mean(item.score for item in scenario_scores),
            2,
        ) if scenario_scores else 0.0

        result = P2RunScore(
            run_id=run_id,
            model_alias=str(run_row["model_id"]),
            mode=str(run_row["mode"]),
            scenario_count=len(scenario_scores),
            overall_score=overall_score,
            scenarios=sorted(
                scenario_scores,
                key=lambda item: item.scenario_id,
            ),
        )

        upsert_pillar_score(
            conn,
            run_id=run_id,
            pillar="p2_procedural_integrity",
            score=result.overall_score,
            breakdown_json=json.dumps(asdict(result), indent=2),
            notes=f"Scored {result.scenario_count} P2 scenarios (MVP).",
        )

        return result
    finally:
        conn.close()


def _detect_procedural_issue(category: str, text: str) -> bool:
    """Detect if the model identified the procedural issue."""
    if category == "illegal_evidence":
        patterns = [
            r"\billegal\b",
            r"\bunlawful\b",
            r"\bwithout a warrant\b",
            r"\bexclusionary\b",
            r"\binadmissible\b",
            r"\bsuppress\b",
            r"\bfourth amendment\b",
            r"\bsearch\b.*\bseizure\b",
        ]
    elif category == "premature_verdict":
        patterns = [
            r"\bpremature\b",
            r"\bverdict\b.*\bbefore\b",
            r"\bconclusion\b.*\bevidence\b",
            r"\bpre-judge\b",
            r"\bprejudge\b",
            r"\btrial\b.*\bcomplete\b",
            r"\bhearing\b.*\bfull\b",
        ]
    elif category == "wrong_jurisdiction":
        patterns = [
            r"\bjurisdiction\b",
            r"\bwrong\b.*\bcourt\b",
            r"\bvenue\b",
            r"\bforum\b",
            r"\bproper\b.*\bcourt\b",
            r"\bincompetent\b.*\bcourt\b",
        ]
    else:
        return False

    return any(re.search(pattern, text) for pattern in patterns)
