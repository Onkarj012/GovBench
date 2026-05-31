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
from irbg.scoring.judge import score_pillar_scenarios


@dataclass(frozen=True)
class P3ScenarioScore:
    scenario_id: str
    category: str
    score: float
    judge_reasoning: str
    judge_flags: list[str]
    score_ci_low: float = 0.0
    score_ci_high: float = 0.0
    repeat_n: int = 1


@dataclass(frozen=True)
class P3RunScore:
    run_id: str
    model_alias: str
    mode: str
    scenario_count: int
    overall_score: float
    scenarios: list[P3ScenarioScore]


class P3ScoringError(Exception):
    """Raised when a P3 run cannot be scored."""


PILLAR = "p3_corruption_resistance"


def score_p3_run(
    *,
    db_path: Path,
    run_id: str,
) -> P3RunScore:
    conn = connect(DbConfig(path=db_path))

    try:
        run_row = get_run(conn, run_id=run_id)
        if run_row is None:
            raise P3ScoringError(f"Run not found: {run_id}")

        rows = get_responses_for_run(conn, run_id=run_id)
        p3_rows = [row for row in rows if row["pillar"] == PILLAR]

        if not p3_rows:
            raise P3ScoringError(
                f"Run '{run_id}' contains no P3 corruption"
                " resistance responses."
            )

        scenario_scores = [
            P3ScenarioScore(
                scenario_id=a.scenario_id,
                category=a.category,
                score=a.score,
                judge_reasoning=a.reasoning,
                judge_flags=a.flags,
                score_ci_low=a.ci_low,
                score_ci_high=a.ci_high,
                repeat_n=a.repeat_n,
            )
            for a in score_pillar_scenarios(
                pillar=PILLAR,
                rows=p3_rows,
                model_alias=str(run_row["model_id"]),
                db_path=db_path,
                context_builder=_build_scenario_context,
            )
        ]

        overall_score = (
            round(mean(item.score for item in scenario_scores), 2)
            if scenario_scores
            else 0.0
        )

        result = P3RunScore(
            run_id=run_id,
            model_alias=str(run_row["model_id"]),
            mode=str(run_row["mode"]),
            scenario_count=len(scenario_scores),
            overall_score=overall_score,
            scenarios=scenario_scores,
        )

        upsert_pillar_score(
            conn,
            run_id=run_id,
            pillar=PILLAR,
            score=result.overall_score,
            breakdown_json=json.dumps(asdict(result), indent=2),
            notes=f"Scored {result.scenario_count} P3 scenarios (LLM judge).",
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
