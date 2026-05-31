from __future__ import annotations

import json
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
from irbg.scoring.judge import JudgeScoringError, judge_response


@dataclass(frozen=True)
class P4ScenarioScore:
    scenario_id: str
    category: str
    score: float
    judge_reasoning: str
    judge_flags: list[str]


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


PILLAR = "p4_jurisdictional_awareness"


def score_p4_run(
    *,
    db_path: Path,
    run_id: str,
) -> P4RunScore:
    conn = connect(DbConfig(path=db_path))

    try:
        run_row = get_run(conn, run_id=run_id)
        if run_row is None:
            raise P4ScoringError(f"Run not found: {run_id}")

        rows = get_responses_for_run(conn, run_id=run_id)
        p4_rows = [row for row in rows if row["pillar"] == PILLAR]

        if not p4_rows:
            raise P4ScoringError(
                f"Run '{run_id}' contains no P4 jurisdictional"
                " awareness responses."
            )

        scenario_scores: list[P4ScenarioScore] = []

        for row in p4_rows:
            scenario_id = str(row["scenario_id"])
            category = str(row["category"])
            text = (row["raw_response"] or "").strip()

            context = _build_scenario_context(row)
            try:
                verdict = judge_response(
                    pillar=PILLAR,
                    scenario_context=context,
                    response_text=text,
                    model_alias=str(run_row["model_id"]),
                    db_path=db_path,
                )
            except JudgeScoringError:
                verdict = judge_response(
                    pillar=PILLAR,
                    scenario_context=context,
                    response_text="",
                )

            scenario_scores.append(
                P4ScenarioScore(
                    scenario_id=scenario_id,
                    category=category,
                    score=verdict.score,
                    judge_reasoning=verdict.reasoning,
                    judge_flags=verdict.flags,
                )
            )

        overall_score = (
            round(mean(item.score for item in scenario_scores), 2)
            if scenario_scores
            else 0.0
        )

        result = P4RunScore(
            run_id=run_id,
            model_alias=str(run_row["model_id"]),
            mode=str(run_row["mode"]),
            scenario_count=len(scenario_scores),
            overall_score=overall_score,
            scenarios=sorted(
                scenario_scores, key=lambda item: item.scenario_id
            ),
        )

        upsert_pillar_score(
            conn,
            run_id=run_id,
            pillar=PILLAR,
            score=result.overall_score,
            breakdown_json=json.dumps(asdict(result), indent=2),
            notes=f"Scored {result.scenario_count} P4 scenarios (LLM judge).",
        )

        return result
    finally:
        conn.close()


def _build_scenario_context(row) -> str:
    system = row["system_prompt_sent"] or ""
    user = row["user_prompt_sent"] or ""
    jurisdiction = row["jurisdiction"] or "unknown"
    return (
        f"Jurisdiction: {jurisdiction}\n"
        f"System Prompt: {system}\n"
        f"User Prompt: {user}"
    )
