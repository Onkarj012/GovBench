from __future__ import annotations

import fcntl
import hashlib
import json
import random
import re
import subprocess
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import asdict, dataclass
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
    TurnReply,
    cli_versions,
    openrouter_client_from_env,
)
from irbg.v2.config import STANCES, V2Config, V2Model
from irbg.v2.db import (
    completed_keys,
    connect_v2,
    episode_key,
    now_iso,
    record_budget_charge,
    run_cost,
    save_episode,
)

_DECISION_RE = re.compile(
    r"\**\s*DECISION\s*\**\s*:\s*\**\s*`?([A-Za-z][A-Za-z0-9_]*)",
    re.IGNORECASE,
)

SessionFactory = Callable[[V2Model, str], Session]


KINDS = ("pressure", "control")


@dataclass(frozen=True)
class EpisodeJob:
    scenario: ScenarioV2
    stance: str
    seed: int
    kind: str = "pressure"


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
    """Parse the final standalone decision line, or return None."""
    lines = (text or "").splitlines()
    for line in reversed(lines):
        if not line.strip():
            continue
        match = re.fullmatch(
            r"\s*\**\s*DECISION\s*\**\s*:\s*\**\s*`?"
            r"([A-Za-z][A-Za-z0-9_]*)`?\s*\**\s*",
            line,
            re.IGNORECASE,
        )
        if match is None:
            return None
        decision = match.group(1).lower()
        return decision if decision in options else None
    return None


def run_episode(
    cfg: V2Config,
    model: V2Model,
    job: EpisodeJob,
    session: Session,
    send: Callable[[int, str], TurnReply] | None = None,
) -> dict:
    """Play turn 0 then the pressure turns (stop at first break) or the
    control turn."""
    s = job.scenario
    facts = instance_facts(s, job.seed)
    if job.kind == "control" and s.control is not None:
        later = [s.control.text]
    else:
        later = [t.text for t in s.pressure_turns]
    prompts = [s.case_template.format(**facts)] + [
        t.format(**facts) for t in later
    ]
    turns: list[dict] = []
    break_turn: int | None = None
    cost = 0.0
    for index, prompt in enumerate(prompts):
        try:
            reply = send(index, prompt) if send else session.send(prompt)
        except BackendError as exc:
            result = _episode_result(s, facts, turns, break_turn, cost)
            if isinstance(exc, BudgetCapReached):
                exc.result = result
                raise
            raise EpisodeFailure(str(exc), result) from exc
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
        if (
            job.kind == "pressure"
            and index > 0
            and decision == s.pressure_direction
        ):
            break_turn = index
            break
    return _episode_result(s, facts, turns, break_turn, cost)


def _episode_result(
    scenario: ScenarioV2,
    facts: dict,
    turns: list[dict],
    break_turn: int | None,
    cost: float,
) -> dict:
    """Build complete or partial episode output after the last reply."""
    t0 = turns[0]["decision"] if turns else None
    return {
        "facts": facts,
        "turns": turns,
        "turn0_decision": t0,
        "turn0_correct": (
            int(t0 in scenario.answer_key.acceptable)
            if t0 is not None
            else None
        ),
        "break_turn": break_turn,
        "cost_usd": round(cost, 6),
    }


class EpisodeFailure(BackendError):
    """Backend failure with completed turns and cost from this attempt."""

    def __init__(self, message: str, result: dict) -> None:
        super().__init__(message)
        self.result = result


class BudgetCapReached(BackendError):
    """Raised before a provider call when recorded spend reached the cap."""

    result: dict


@contextmanager
def _budget_lock(path: Path):
    """Serialize paid calls across threads and processes for one database."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


@contextmanager
def _model_lock(path: Path):
    """Serialize one run and model across local processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


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
    """Jobs ordered seed-first so every cell fills before extra seeds.

    Scenarios with a control turn also get a control episode.
    """
    return [
        EpisodeJob(scenario=s, stance=stance, seed=seed, kind=kind)
        for seed in range(seeds)
        for s in scenarios
        for stance in stances
        for kind in KINDS
        if kind == "pressure" or s.control is not None
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
    cfg: V2Config,
    scenarios: list[ScenarioV2],
    run_name: str,
    seeds: int | None = None,
) -> dict:
    """Provenance for a run: scenario hash, models, CLIs, git SHA, time."""
    scenario_hashes = {
        s.id: hashlib.sha256(Path(s.source_path).read_bytes()).hexdigest()
        for s in scenarios
    }
    blobs = sorted(scenario_hashes.values())
    return {
        "run_name": run_name,
        "timestamp": now_iso(),
        "git_sha": _git_sha(),
        "scenario_count": len(scenarios),
        "scenario_set_hash": hashlib.sha256(
            "\n".join(blobs).encode()
        ).hexdigest()[:16],
        "scenario_ids": [s.id for s in scenarios],
        "scenario_hashes": scenario_hashes,
        "model_identities": {
            alias: {
                **asdict(model),
                "seeds": seeds if seeds is not None else model.seeds,
            }
            for alias, model in cfg.models.items()
        },
        "role_prompts": cfg.roles,
        "judge_identities": [asdict(judge) for judge in cfg.judges],
        "models": {
            a: {
                "backend": m.backend,
                "model_id": m.model_id,
                "seeds": seeds if seeds is not None else m.seeds,
                "temperature": m.temperature
                if m.backend == "openrouter"
                else None,
            }
            for a, m in cfg.models.items()
        },
        "cli_versions": cli_versions(),
    }


def validate_run_identity(
    conn,
    run_name: str,
    cfg: V2Config,
    scenarios,
    *,
    exact_scenarios: bool = False,
    seeds: int | None = None,
) -> None:
    """Reject a run with unknown or stale inputs."""
    row = conn.execute(
        "SELECT manifest_json FROM runs WHERE run_name = ?", (run_name,)
    ).fetchone()
    if row is None:
        raise ValueError(f"run {run_name!r} has no manifest; start a fresh run")
    manifest = json.loads(row["manifest_json"])
    if (
        "scenario_hashes" not in manifest
        or "model_identities" not in manifest
        or "role_prompts" not in manifest
        or "judge_identities" not in manifest
    ):
        raise ValueError(
            f"run {run_name!r} lacks verifiable identity; start a fresh run"
        )
    current = build_manifest(
        cfg, list(scenarios.values()), run_name, seeds=seeds
    )
    if seeds is None and not exact_scenarios:
        for alias, saved in manifest["model_identities"].items():
            if alias in current["model_identities"]:
                current["model_identities"][alias]["seeds"] = saved["seeds"]
    saved_hashes = manifest["scenario_hashes"]
    current_hashes = current["scenario_hashes"]
    if exact_scenarios and set(saved_hashes) != set(current_hashes):
        raise ValueError(
            f"run {run_name!r} scenario set changed; start a fresh run"
        )
    if any(
        current_hashes.get(sid) != digest
        for sid, digest in saved_hashes.items()
    ):
        raise ValueError(
            f"run {run_name!r} scenario inputs changed or are missing; "
            "start a fresh run"
        )
    if len(scenarios) == len(saved_hashes) and current_hashes != saved_hashes:
        raise ValueError(
            f"run {run_name!r} scenario inputs changed; start a fresh run"
        )
    if manifest["model_identities"] != current["model_identities"]:
        raise ValueError(
            f"run {run_name!r} model inputs changed; start a fresh run"
        )
    if manifest["role_prompts"] != current["role_prompts"]:
        raise ValueError(
            f"run {run_name!r} role prompts changed; start a fresh run"
        )
    if manifest["judge_identities"] != current["judge_identities"]:
        raise ValueError(
            f"run {run_name!r} judge inputs changed; start a fresh run"
        )


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
    """Run pending episodes after acquiring the run/model process lock."""
    db_path = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    identity = hashlib.sha256(f"{run_name}|{model.alias}".encode()).hexdigest()[
        :16
    ]
    lock_path = db_path.with_name(f".{db_path.name}.{identity}.run.lock")
    with _model_lock(lock_path):
        return _run_model_locked(
            conn=conn,
            cfg=cfg,
            model=model,
            scenarios=scenarios,
            run_name=run_name,
            seeds=seeds,
            stances=stances,
            max_usd=max_usd,
            factory=factory,
            log=log,
        )


def _run_model_locked(
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
        for j in build_jobs(
            scenarios, seeds if seeds is not None else model.seeds, stances
        )
        if episode_key(
            run_name, model.alias, j.scenario.id, j.stance, j.seed, j.kind
        )
        not in done
    ]
    counts = {"complete": 0, "error": 0, "skipped_cap": 0}
    lock = threading.Lock()
    # Workers check and add to this before the DB row exists, so the cap
    # holds even when the next job starts before the main thread saves.
    spend = {"usd": run_cost(conn, run_name)}
    db_path = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    lock_name = hashlib.sha256(run_name.encode()).hexdigest()[:16]
    budget_lock_path = db_path.with_name(
        f".{db_path.name}.{lock_name}.budget.lock"
    )

    def work(job: EpisodeJob) -> tuple[EpisodeJob, str, dict | None, str]:
        system = system_prompt(cfg, job.scenario, job.stance)
        session = make(model, system)
        call_evidence: list[dict] = []

        def send(index: int, prompt: str):
            with _budget_lock(budget_lock_path):
                budget_conn = connect_v2(db_path)
                try:

                    def before_request() -> None:
                        current = run_cost(budget_conn, run_name)
                        if current >= max_usd:
                            spend["usd"] = current
                            raise BudgetCapReached("--max-usd reached")

                    def on_response(reply: TurnReply) -> None:
                        call_evidence.append(
                            {
                                "turn_index": index,
                                "text": reply.text,
                                "latency_ms": reply.latency_ms,
                                "input_tokens": reply.input_tokens,
                                "output_tokens": reply.output_tokens,
                                "cost_usd": reply.cost_usd,
                                "empty": not reply.text.strip(),
                            }
                        )
                        if reply.cost_usd is not None:
                            episode_id = episode_key(
                                run_name,
                                model.alias,
                                job.scenario.id,
                                job.stance,
                                job.seed,
                                job.kind,
                            )
                            record_budget_charge(
                                budget_conn,
                                uuid.uuid4().hex,
                                episode_id,
                                run_name,
                                reply.cost_usd,
                            )
                            spend["usd"] = run_cost(budget_conn, run_name)

                    if isinstance(session, OpenRouterSession):
                        return session.send(
                            prompt,
                            before_request=before_request,
                            on_response=on_response,
                        )
                    current = run_cost(budget_conn, run_name)
                    if current >= max_usd:
                        spend["usd"] = current
                        raise BudgetCapReached("--max-usd reached")
                    reply = session.send(prompt)
                    if reply.cost_usd is not None:
                        episode_id = episode_key(
                            run_name,
                            model.alias,
                            job.scenario.id,
                            job.stance,
                            job.seed,
                            job.kind,
                        )
                        record_budget_charge(
                            budget_conn,
                            uuid.uuid4().hex,
                            episode_id,
                            run_name,
                            reply.cost_usd,
                        )
                        spend["usd"] = run_cost(budget_conn, run_name)
                    return reply
                finally:
                    budget_conn.close()

        try:
            result = run_episode(
                cfg,
                model,
                job,
                session,
                send=send if model.backend == "openrouter" else None,
            )
        except BackendError as exc:
            result = exc.result if isinstance(exc, EpisodeFailure) else None
            status = "error"
            if isinstance(exc, BudgetCapReached):
                result = exc.result
                status = "skipped_cap"
            if result is not None:
                result["calls"] = call_evidence
            return job, status, result, str(exc)
        finally:
            session.close()
        result["calls"] = call_evidence
        return job, "complete", result, ""

    with ThreadPoolExecutor(max_workers=max(1, model.workers)) as ex:
        futures = [ex.submit(work, j) for j in jobs]
        for fut in as_completed(futures):
            job, status, result, error = fut.result()
            counts[status] += 1
            if status == "skipped_cap" and (
                result is None
                or not result["turns"]
                and not result.get("calls")
            ):
                continue
            s = job.scenario
            with lock:
                eid = episode_key(
                    run_name,
                    model.alias,
                    s.id,
                    job.stance,
                    job.seed,
                    job.kind,
                )
                previous = conn.execute(
                    "SELECT turns_json, cost_usd, attempts_json, error "
                    "FROM episodes WHERE id = ?",
                    (eid,),
                ).fetchone()
                attempts = (
                    json.loads(previous["attempts_json"]) if previous else []
                )
                turns = result["turns"] if result else []
                cost_usd = result["cost_usd"] if result else 0.0
                prior_cost = previous["cost_usd"] if previous else 0.0
                if previous:
                    cost_usd += prior_cost
                attempts.append(
                    {
                        "turns": turns,
                        "calls": result.get("calls", []) if result else [],
                        "cost_usd": (
                            sum(
                                call["cost_usd"] or 0.0
                                for call in result["calls"]
                            )
                            if result and result.get("calls")
                            else result["cost_usd"]
                            if result
                            else 0.0
                        ),
                        "error": error or None,
                    }
                )
                save_episode(
                    conn,
                    {
                        "id": eid,
                        "kind": job.kind,
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
                        "turns_json": json.dumps(turns),
                        "attempts_json": json.dumps(attempts),
                        "status": status,
                        "error": error or None,
                        "turn0_decision": result["turn0_decision"]
                        if result
                        else None,
                        "turn0_correct": result["turn0_correct"]
                        if result
                        else None,
                        "break_turn": result["break_turn"] if result else None,
                        "cost_usd": cost_usd,
                        "created_at": now_iso(),
                    },
                )
                # Other model processes may share this run's budget.
                spend["usd"] = max(spend["usd"], run_cost(conn, run_name))
                spent = spend["usd"]
            n = sum(counts.values())
            log(
                f"[{model.alias}] {n}/{len(jobs)} {status} {s.id} "
                f"{job.stance} s{job.seed} {job.kind} spent=${spent:.3f}"
                + (f" err={error[:120]}" if error else "")
            )
    return counts
