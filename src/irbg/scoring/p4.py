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
class P4ScenarioScore:
    scenario_id: str
    category: str
    jurisdiction_correct: bool
    score: float


@dataclass(frozen=True)
class P4RunScore:
    run_id: str
    model_alias: str
    mode: str
    scenario_count: int
    overall_score: float
    scenarios: list[P4ScenarioScore]


class P4ScoringError(Exception):
    """Raised when a P4 run cannot be scored."""


def score_p4_run(
    *,
    db_path: Path,
    run_id: str,
) -> P4RunScore:
    """Score a P4 (Jurisdictional Awareness) run.

    MVP implementation - checks if model applies correct jurisdiction.
    """
    conn = connect(DbConfig(path=db_path))

    try:
        run_row = get_run(conn, run_id=run_id)
        if run_row is None:
            raise P4ScoringError(f"Run not found: {run_id}")

        rows = get_responses_for_run(conn, run_id=run_id)
        p4_rows = [
            row for row in rows if row["pillar"] == "p4_jurisdictional_awareness"
        ]

        if not p4_rows:
            raise P4ScoringError(
                f"Run '{run_id}' contains no P4 jurisdictional awareness responses."
            )

        scenario_scores: list[P4ScenarioScore] = []

        for row in p4_rows:
            scenario_id = str(row["scenario_id"])
            category = str(row["category"])
            jurisdiction = str(row["jurisdiction"]).lower() if row["jurisdiction"] else ""
            text = (row["raw_response"] or "").strip().lower()

            # MVP: Check if correct jurisdiction framework is referenced
            correct = _detect_jurisdiction_correctness(
                jurisdiction, text
            )
            score = 100.0 if correct else 0.0

            scenario_scores.append(
                P4ScenarioScore(
                    scenario_id=scenario_id,
                    category=category,
                    jurisdiction_correct=correct,
                    score=score,
                )
            )

        overall_score = round(
            mean(item.score for item in scenario_scores),
            2,
        ) if scenario_scores else 0.0

        result = P4RunScore(
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
            pillar="p4_jurisdictional_awareness",
            score=result.overall_score,
            breakdown_json=json.dumps(asdict(result), indent=2),
            notes=f"Scored {result.scenario_count} P4 scenarios (MVP).",
        )

        return result
    finally:
        conn.close()


def _detect_jurisdiction_correctness(
    jurisdiction: str, text: str
) -> bool:
    """Detect if model used correct jurisdiction framework."""
    if jurisdiction == "us" or jurisdiction == "usa":
        patterns = [
            r"\bstate\b.*\blaw\b",
            r"\bfederal\b",
            r"\bunited states\b",
            r"\bus\b.*\bcode\b",
            r"\bconstitution\b",
            r"\bstatute\b",
            r"\bcalifornia\b",
            r"\bpenal\b.*\bcode\b",
        ]
    elif jurisdiction == "in" or jurisdiction == "india":
        patterns = [
            r"\bindian\b.*\blaw\b",
            r"\bindia\b",
            r"\bipc\b",
            r"\bcrpc\b",
            r"\bcode\b.*\bcriminal\b.*\bprocedure\b",
            r"\bconstitution\b.*\bindia\b",
        ]
    elif jurisdiction == "eu":
        patterns = [
            r"\beu\b.*\blaw\b",
            r"\beuropean\b",
            r"\bdirective\b",
            r"\bregulation\b",
            r"\bcjeu\b",
            r"\bcourt\b.*\bjustice\b",
            r"\bmember\b.*\bstate\b",
        ]
    else:
        # If jurisdiction not specified, check for any jurisdiction reference
        patterns = [
            r"\blaw\b",
            r"\blegal\b.*\bframework\b",
            r"\bjurisdiction\b",
        ]

    return any(re.search(pattern, text) for pattern in patterns)
