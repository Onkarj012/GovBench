from __future__ import annotations

import hashlib
import json
import random
import re
import subprocess
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from irbg.engine.fact_generator import (
    parse_fact_space,
    sample_instance,
    seed_for,
)
from irbg.paths import PROJECT_ROOT
from irbg.scenarios.v2 import ScenarioV2
from irbg.v2.backends import (
    BackendError,
    ClaudeCodeSession,
    CodexSession,
    OpenRouterSession,
    Session,
    cli_versions,
    openrouter_client_from_env,
)
from irbg.v2.config import STANCES, V2Config, V2Model
from irbg.v2.db import (
    completed_keys,
    episode_key,
    now_iso,
    run_cost,
    save_episode,
)

_DECISION_RE = re.compile(
    r"\**\s*DECISION\s*\**\s*:\s*\**\s*`?([A-Za-z][A-Za-z0-9_]*)",
    re.IGNORECASE,
)

SessionFactory = Callable[[V2Model, str], Session]


@dataclass(frozen=True)
class EpisodeJob:
    scenario: ScenarioV2
    stance: str
    seed: int


def decision_contract(options: tuple[str, ...]) -> str:
    """Instruction appended to the role prompt so decisions parse by regex."""
    return (
        "End every reply with exactly one final line in this form:\n"
        f"DECISION: <one of: {' | '.join(options)}>\n"
        "Use one of those words exactly."
    )


def system_prompt(cfg: V2Config, s: ScenarioV2, stance: str) -> str:
    """Role prompt for the stance plus the decision contract."""
    return f"{cfg.role_prompt(s.role, stance)}\n\n" + decision_contract(
        s.options
    )


def instance_facts(s: ScenarioV2, seed: int) -> dict:
    """Seeded facts for one scenario instance."""
    if not s.fact_space:
        return {}
    rng = random.Random(seed_for(s.id, seed))
    return sample_instance(parse_fact_space(s.fact_space), rng=rng)


def parse_decision(text: str, options: tuple[str, ...]) -> str | None:
    """Last valid DECISION line in a reply, or None."""
    for raw in reversed(_DECISION_RE.findall(text or "")):
        d = raw.lower()
        if d in options:
            return d
    return None


def run_episode(
    cfg: V2Config, model: V2Model, job: EpisodeJob, session: Session
) -> dict:
    """Play turn 0 and the pressure turns; stop at the first break."""
    s = job.scenario
    facts = instance_facts(s, job.seed)
    prompts = [s.case_template.format(**facts)] + [
        t.text.format(**facts) for t in s.pressure_turns
    ]
    turns: list[dict] = []
    break_turn: int | None = None
    cost = 0.0
    for index, prompt in enumerate(prompts):
        reply = session.send(prompt)
        decision = parse_decision(reply.text, s.options)
        cost += reply.cost_usd or 0.0
        turns.append(
            {
                "index": index,
                "prompt": prompt,
                "text": reply.text,
                "decision": decision,
                "latency_ms": reply.latency_ms,
                "input_tokens": reply.input_tokens,
                "output_tokens": reply.output_tokens,
                "cost_usd": reply.cost_usd,
            }
        )
        if index > 0 and decision == s.pressure_direction:
            break_turn = index
            break
    t0 = turns[0]["decision"]
    return {
        "facts": facts,
        "turns": turns,
        "turn0_decision": t0,
        "turn0_correct": int(t0 == s.answer_key.decision),
        "break_turn": break_turn,
        "cost_usd": round(cost, 6),
    }


def default_session_factory() -> SessionFactory:
    """Session factory that shares one OpenRouter client across threads."""
    client_box: dict[str, object] = {}
    lock = threading.Lock()

    def make(model: V2Model, system: str) -> Session:
        if model.backend == "codex":
            return CodexSession(model_id=model.model_id, system=system)
        if model.backend == "claude_code":
            return ClaudeCodeSession(model_id=model.model_id, system=system)
        with lock:
            if "c" not in client_box:
                client_box["c"] = openrouter_client_from_env()
        return OpenRouterSession(
            client=client_box["c"],  # type: ignore[arg-type]
            model_id=model.model_id,
            system=system,
            max_tokens=model.max_tokens,
            temperature=model.temperature,
            price_input=model.price_input,
            price_output=model.price_output,
        )

    return make


def build_jobs(
    scenarios: list[ScenarioV2], seeds: int, stances: tuple[str, ...]
) -> list[EpisodeJob]:
    """Jobs ordered seed-first so every cell fills before extra seeds."""
    return [
        EpisodeJob(scenario=s, stance=stance, seed=seed)
        for seed in range(seeds)
        for s in scenarios
        for stance in stances
    ]


def _git_sha() -> str:
    """Current git HEAD, for provenance."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def build_manifest(
    cfg: V2Config, scenarios: list[ScenarioV2], run_name: str
) -> dict:
    """Provenance for a run: scenario hash, models, CLIs, git SHA, time."""
    blobs = sorted(
        hashlib.sha256(Path(s.source_path).read_bytes()).hexdigest()
        for s in scenarios
    )
    return {
        "run_name": run_name,
        "timestamp": now_iso(),
        "git_sha": _git_sha(),
        "scenario_count": len(scenarios),
        "scenario_set_hash": hashlib.sha256(
            "\n".join(blobs).encode()
        ).hexdigest()[:16],
        "scenario_ids": [s.id for s in scenarios],
        "models": {
            a: {
                "backend": m.backend,
                "model_id": m.model_id,
                "seeds": m.seeds,
                "temperature": m.temperature
                if m.backend == "openrouter"
                else None,
            }
            for a, m in cfg.models.items()
        },
        "cli_versions": cli_versions(),
    }


def run_model(
    *,
    conn,
    cfg: V2Config,
    model: V2Model,
    scenarios: list[ScenarioV2],
    run_name: str,
    seeds: int | None = None,
    stances: tuple[str, ...] = STANCES,
    max_usd: float = 10.0,
    factory: SessionFactory | None = None,
    log: Callable[[str], None] = print,
) -> dict[str, int]:
    """Run all pending episodes for one model; resumable and cost-capped."""
    make = factory or default_session_factory()
    done = completed_keys(conn, run_name)
    jobs = [
        j
        for j in build_jobs(scenarios, seeds or model.seeds, stances)
        if episode_key(run_name, model.alias, j.scenario.id, j.stance, j.seed)
        not in done
    ]
    counts = {"complete": 0, "error": 0, "skipped_cap": 0}
    lock = threading.Lock()
    # Workers check and add to this before the DB row exists, so the cap
    # holds even when the next job starts before the main thread saves.
    spend = {"usd": run_cost(conn, run_name)}

    def work(job: EpisodeJob) -> tuple[EpisodeJob, str, dict | None, str]:
        with lock:
            if spend["usd"] >= max_usd:
                return job, "skipped_cap", None, ""
        system = system_prompt(cfg, job.scenario, job.stance)
        session = make(model, system)
        try:
            result = run_episode(cfg, model, job, session)
        except BackendError as exc:
            return job, "error", None, str(exc)
        finally:
            session.close()
        with lock:
            spend["usd"] += result["cost_usd"]
        return job, "complete", result, ""

    with ThreadPoolExecutor(max_workers=max(1, model.workers)) as ex:
        futures = [ex.submit(work, j) for j in jobs]
        for fut in as_completed(futures):
            job, status, result, error = fut.result()
            counts[status] += 1
            if status == "skipped_cap":
                continue
            s = job.scenario
            with lock:
                save_episode(
                    conn,
                    {
                        "id": episode_key(
                            run_name, model.alias, s.id, job.stance, job.seed
                        ),
                        "run_name": run_name,
                        "model_alias": model.alias,
                        "backend": model.backend,
                        "scenario_id": s.id,
                        "role": s.role,
                        "pressure": s.pressure,
                        "split": s.split,
                        "review_status": s.review_status,
                        "stance": job.stance,
                        "seed": job.seed,
                        "instance_json": json.dumps(
                            result["facts"] if result else {}
                        ),
                        "system_prompt": system_prompt(cfg, s, job.stance),
                        "turns_json": json.dumps(
                            result["turns"] if result else []
                        ),
                        "status": status,
                        "error": error or None,
                        "turn0_decision": result["turn0_decision"]
                        if result
                        else None,
                        "turn0_correct": result["turn0_correct"]
                        if result
                        else None,
                        "break_turn": result["break_turn"] if result else None,
                        "cost_usd": result["cost_usd"] if result else 0.0,
                        "created_at": now_iso(),
                    },
                )
                # Other model processes may share this run's budget.
                spend["usd"] = max(spend["usd"], run_cost(conn, run_name))
                spent = spend["usd"]
            n = sum(counts.values())
            log(
                f"[{model.alias}] {n}/{len(jobs)} {status} {s.id} "
                f"{job.stance} s{job.seed} spent=${spent:.3f}"
                + (f" err={error[:120]}" if error else "")
            )
    return counts
