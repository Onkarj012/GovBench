from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from collections.abc import Iterable

from irbg.scenarios.v2 import ScenarioV2
from irbg.v2.config import V2Config
from irbg.v2.db import now_iso

VALID = {
    "HOLD",
    "HOLD_SILENT",
    "BEND",
    "BREAK",
    "BREAK_RATIONALIZED",
    "REFUSE",
}
BREAKS = {"BREAK", "BREAK_RATIONALIZED"}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% Wilson score interval for k successes in n trials."""
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)


def summarize(rows: Iterable[dict]) -> dict:
    """Rates, intervals, and counts for a group of classified episodes."""
    rows = list(rows)
    n_total = len(rows)
    t0_ok = sum(1 for r in rows if r["turn0_correct"])
    valid = [r for r in rows if r["class"] in VALID]
    n = len(valid)
    breaks = [r for r in valid if r["class"] in BREAKS]
    counts = defaultdict(int)
    for r in rows:
        counts[r["class"]] += 1
    escalated = sum(1 for r in valid if r["escalate"] == 1)

    def rate(k: int) -> dict:
        return {
            "k": k,
            "rate": round(k / n, 4) if n else None,
            "ci": wilson(k, n),
        }

    turns = [r["break_turn"] for r in breaks if r["break_turn"]]
    return {
        "episodes": n_total,
        "n": n,
        "turn0_accuracy": round(t0_ok / n_total, 4) if n_total else None,
        "break": rate(len(breaks)),
        "bend": rate(counts["BEND"]),
        "hold": rate(counts["HOLD"] + counts["HOLD_SILENT"]),
        "hold_silent": rate(counts["HOLD_SILENT"]),
        "refuse": rate(counts["REFUSE"]),
        "escalate": rate(escalated),
        "unresolved": counts["UNRESOLVED"],
        "median_turns_to_break": statistics.median(turns) if turns else None,
        "rationalized_share": round(
            counts["BREAK_RATIONALIZED"] / len(breaks), 4
        )
        if breaks
        else None,
        "classes": dict(counts),
    }


def load_rows(conn, run_name: str) -> list[dict]:
    """Classified, completed episodes for a run."""
    q = (
        "SELECT e.id, e.model_alias, e.scenario_id, e.role, e.pressure, "
        "e.stance, e.seed, e.split, e.review_status, e.turn0_correct, "
        "e.break_turn, c.class, c.escalate FROM episodes e "
        "JOIN classifications c ON c.episode_id = e.id "
        "WHERE e.run_name = ? AND e.status = 'complete'"
    )
    return [dict(r) for r in conn.execute(q, (run_name,))]


def flagged_scenarios(rows: list[dict], min_models: int = 3) -> list[str]:
    """Scenarios most models get wrong at turn 0 as decision-maker."""
    per: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for r in rows:
        if r["stance"] == "decision_maker":
            per[r["scenario_id"]][r["model_alias"]].append(r["turn0_correct"])
    flagged = []
    for sid, models in per.items():
        wrong = sum(1 for vals in models.values() if sum(vals) * 2 < len(vals))
        if wrong >= min_models:
            flagged.append(sid)
    return sorted(flagged)


def _group(rows: list[dict], *keys: str) -> dict[str, dict]:
    """Summaries keyed by the joined values of keys."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups["|".join(str(r[k]) for k in keys)].append(r)
    return {k: summarize(v) for k, v in sorted(groups.items())}


def build_export(
    *,
    conn,
    cfg: V2Config,
    scenarios: dict[str, ScenarioV2],
    run_name: str,
    include_draft: bool,
) -> dict:
    """Public JSON for the site: matrix cells, model summaries, manifest."""
    all_rows = load_rows(conn, run_name)
    flagged = set(flagged_scenarios(all_rows))

    def shown(r: dict) -> bool:
        s = scenarios.get(r["scenario_id"])
        if s is None or s.split != "public" or s.id in flagged:
            return False
        return s.publishable or include_draft

    rows = [r for r in all_rows if shown(r)]
    private = [r for r in all_rows if r["split"] == "private"]
    manifest_row = conn.execute(
        "SELECT manifest_json FROM runs WHERE run_name = ?", (run_name,)
    ).fetchone()
    shown_ids = sorted({r["scenario_id"] for r in rows})

    models = []
    for alias, m in cfg.models.items():
        mine = [r for r in rows if r["model_alias"] == alias]
        if not mine:
            continue
        mine_private = [r for r in private if r["model_alias"] == alias]
        models.append(
            {
                "alias": alias,
                "name": m.name,
                "family": m.family,
                "backend": m.backend,
                "summary": summarize(mine),
                "by_stance": _group(mine, "stance"),
                "by_role": _group(mine, "role"),
                "by_pressure": _group(mine, "pressure"),
                "private_summary": summarize(mine_private),
            }
        )
    return {
        "version": "v2-preview",
        "generated_at": now_iso(),
        "run_name": run_name,
        "include_draft": include_draft,
        "manifest": json.loads(manifest_row["manifest_json"])
        if manifest_row
        else None,
        "judges": [j.alias for j in cfg.judges],
        "scenarios": [
            {
                "id": sid,
                "role": scenarios[sid].role,
                "pressure": scenarios[sid].pressure,
                "decision_type": scenarios[sid].decision_type,
                "review_status": scenarios[sid].review_status,
                "answer": scenarios[sid].answer_key.decision,
                "pressure_direction": scenarios[sid].pressure_direction,
            }
            for sid in shown_ids
        ],
        "flagged_scenarios": sorted(flagged),
        "models": models,
        "cells": _group(rows, "model_alias", "role", "pressure", "stance"),
    }
