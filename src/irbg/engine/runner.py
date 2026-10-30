from __future__ import annotations

import hashlib
import json
import os
import random
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from dataclasses import replace as _dc_replace
from pathlib import Path

from irbg.config import get_model_config
from irbg.db.operations import (
    DbConfig,
    connect,
    create_benchmark_run,
    insert_response,
    mark_benchmark_run_completed,
    mark_benchmark_run_failed,
    upsert_model,
    upsert_run_manifest,
    upsert_scenario,
    upsert_scenario_record,
)
from irbg.engine.fact_generator import (
    FactGenerationError,
    parse_fact_space,
    sample_instance,
    seed_for,
)
from irbg.engine.prompt_builder import render_prompt
from irbg.engine.provider import OpenRouterClient
from irbg.engine.types import ChatMessage, ProviderResponse
from irbg.engine.variant_generator import (
    generate_prompts_for_template,
    generate_single_prompt_for_variant,
)
from irbg.scenarios.discovery import load_template_files
from irbg.scenarios.loader import load_scenario
from irbg.scenarios.template_loader import (
    ScenarioTemplateLoadError,
    load_scenario_template,
)
from irbg.scenarios.template_models import RenderedPrompt, ScenarioTemplate

# Token budgets are opt-in per pillar (Phase 1.4). P5 (transparency) and
# P6 (minority protection) are intentionally uncapped — their rubrics
# reward elaboration — and fall back to the model's configured max_tokens.
# Budgets are sized to leave room for reasoning models' hidden tokens plus a
# full answer; the per-call cap is min(model.max_tokens, budget).
PILLAR_TOKEN_BUDGETS: dict[str, int] = {
    "p1_demographic_consistency": 1024,
    "p2_procedural_integrity": 1024,
    "p3_corruption_resistance": 1024,
    "p4_jurisdictional_awareness": 1024,
}


def _effective_max_tokens(
    pillar: str | None,
    model_max_tokens: int,
) -> int:
    if pillar is None:
        return model_max_tokens
    budget = PILLAR_TOKEN_BUDGETS.get(pillar)
    if budget is None:
        return model_max_tokens
    return min(model_max_tokens, budget)


def _reasoning_param(model) -> dict | None:
    """Map model.reasoning config to an OpenRouter reasoning parameter."""
    if model.reasoning is None:
        return None
    if model.reasoning.lower() in {"off", "none", "false", "disabled"}:
        return {"enabled": False}
    return {"effort": model.reasoning}


def _usage_kwargs(provider_response, model) -> dict:
    """Full per-call telemetry for insert_response.

    Uses the provider-reported cost when available, otherwise computes it
    from the configured per-1M-token pricing.
    """
    cost = provider_response.cost_usd
    if cost is None and (model.price_input or model.price_output):
        cost = round(
            provider_response.input_tokens / 1_000_000 * model.price_input
            + provider_response.output_tokens / 1_000_000 * model.price_output,
            6,
        )
    return {
        "response_tokens": provider_response.total_tokens,
        "prompt_tokens": provider_response.input_tokens,
        "completion_tokens": provider_response.output_tokens,
        "reasoning_tokens": provider_response.reasoning_tokens,
        "cached_tokens": provider_response.cached_tokens,
        "cost_usd": cost,
        "finish_reason": provider_response.finish_reason,
        "reasoning_text": provider_response.reasoning_text,
    }


@dataclass(frozen=True)
class RunOnceResult:
    run_id: str
    response_id: str
    model_alias: str
    scenario_id: str
    success: bool
    error: str | None = None


@dataclass(frozen=True)
class RunBatchResult:
    run_id: str
    model_alias: str
    scenario_id: str
    mode: str
    total_count: int
    success_count: int
    failure_count: int


@dataclass(frozen=True)
class RunFolderResult:
    run_id: str
    model_alias: str
    folder_path: str
    mode: str
    scenario_count: int
    total_prompt_count: int
    success_count: int
    failure_count: int


@dataclass(frozen=True)
class _TurnRecord:
    """One response row's worth of data, produced by a worker thread.

    Carries everything ``insert_response`` needs (minus ``run_id``, which
    the main thread supplies) so workers never touch the shared sqlite
    connection. ``response`` is the raw provider result for this turn.
    """

    scenario_id: str
    variant_id: str | None
    mode: str
    turn_number: int
    system_prompt_sent: str
    user_prompt_sent: str
    instance_json: str | None
    response: ProviderResponse


@dataclass(frozen=True)
class _PromptResult:
    """Outcome of a single rendered prompt (may span several turns)."""

    turns: list[_TurnRecord]
    success: bool


@dataclass(frozen=True)
class _ScenarioWork:
    """Everything a worker produces for one scenario file.

    The main thread consumes this to upsert the scenario record and write
    every response row. Seeding depends only on (template_id, run_seed),
    so a given scenario file yields identical work regardless of which
    worker thread or execution order handles it.
    """

    template_id: str
    pillar: str
    category: str
    jurisdiction: str | None
    difficulty: str | None
    prompt_results: list[_PromptResult]


def run_single_scenario(
    *,
    model_alias: str,
    scenario_file: Path,
    db_path: Path,
    mode: str = "baseline",
) -> RunOnceResult:
    model = get_model_config(model_alias)
    scenario = load_scenario(scenario_file)

    client = _build_client_from_env()
    conn = connect(DbConfig(path=db_path))

    try:
        upsert_model(
            conn,
            id=model.alias,
            name=model.name,
            provider=model.provider,
            model_id=model.model_id,
        )

        upsert_scenario(conn, scenario=scenario)

        config_snapshot = json.dumps(
            {
                "model_alias": model.alias,
                "provider_model_id": model.model_id,
                "scenario_file": str(scenario_file),
                "mode": mode,
            }
        )

        run_id = create_benchmark_run(
            conn,
            model_id=model.alias,
            mode=mode,
            status="running",
            config_snapshot=config_snapshot,
        )

        provider_response = client.chat(
            model_id=model.model_id,
            system_prompt=scenario.system_prompt,
            user_prompt=scenario.user_prompt,
            temperature=model.temperature,
            max_tokens=model.max_tokens,
            top_p=model.top_p,
            reasoning=_reasoning_param(model),
        )

        response_id = insert_response(
            conn,
            run_id=run_id,
            scenario_id=scenario.id,
            variant_id=None,
            mode=mode,
            turn_number=1,
            system_prompt_sent=scenario.system_prompt,
            user_prompt_sent=scenario.user_prompt,
            raw_response=provider_response.text
            if provider_response.success
            else None,
            latency_ms=provider_response.latency_ms,
            **_usage_kwargs(provider_response, model),
        )

        if provider_response.success:
            mark_benchmark_run_completed(conn, run_id=run_id)
        else:
            mark_benchmark_run_failed(conn, run_id=run_id)

        return RunOnceResult(
            run_id=run_id,
            response_id=response_id,
            model_alias=model.alias,
            scenario_id=scenario.id,
            success=provider_response.success,
            error=provider_response.error,
        )
    finally:
        client.close()
        conn.close()


def run_single_template_variant(
    *,
    model_alias: str,
    scenario_file: Path,
    variant_id: str,
    db_path: Path,
    mode: str = "baseline",
) -> RunOnceResult:
    model = get_model_config(model_alias)
    template = load_scenario_template(scenario_file)
    rendered = generate_single_prompt_for_variant(
        template,
        variant_id=variant_id,
        mode=mode,
    )

    client = _build_client_from_env()
    conn = connect(DbConfig(path=db_path))

    try:
        upsert_model(
            conn,
            id=model.alias,
            name=model.name,
            provider=model.provider,
            model_id=model.model_id,
        )

        upsert_scenario_record(
            conn,
            id=template.id,
            pillar=template.pillar,
            category=template.category,
            jurisdiction=template.jurisdiction,
            difficulty=template.difficulty,
        )

        config_snapshot = json.dumps(
            {
                "model_alias": model.alias,
                "provider_model_id": model.model_id,
                "scenario_file": str(scenario_file),
                "mode": mode,
                "variant_id": variant_id,
            }
        )

        run_id = create_benchmark_run(
            conn,
            model_id=model.alias,
            mode=mode,
            status="running",
            config_snapshot=config_snapshot,
        )

        if mode == "adversarial" and template.adversarial_turns:
            response_ids, success, error = _execute_adversarial_sequence(
                client=client,
                conn=conn,
                run_id=run_id,
                model_id=model.model_id,
                rendered=rendered,
                adversarial_turns=template.adversarial_turns,
                temperature=model.temperature,
                max_tokens=_effective_max_tokens(
                    rendered.pillar, model.max_tokens
                ),
                top_p=model.top_p,
                model=model,
            )
            response_id = response_ids[-1]
        else:
            provider_response = client.chat(
                model_id=model.model_id,
                system_prompt=rendered.system_prompt,
                user_prompt=rendered.user_prompt,
                temperature=model.temperature,
                max_tokens=_effective_max_tokens(
                    rendered.pillar, model.max_tokens
                ),
                top_p=model.top_p,
                reasoning=_reasoning_param(model),
            )

            response_id = insert_response(
                conn,
                run_id=run_id,
                scenario_id=template.id,
                variant_id=rendered.variant_id,
                mode=mode,
                turn_number=1,
                system_prompt_sent=rendered.system_prompt,
                user_prompt_sent=rendered.user_prompt,
                raw_response=provider_response.text
                if provider_response.success
                else None,
                latency_ms=provider_response.latency_ms,
                **_usage_kwargs(provider_response, model),
            )
            success = provider_response.success
            error = provider_response.error

        if success:
            mark_benchmark_run_completed(conn, run_id=run_id)
        else:
            mark_benchmark_run_failed(conn, run_id=run_id)

        return RunOnceResult(
            run_id=run_id,
            response_id=response_id,
            model_alias=model.alias,
            scenario_id=template.id,
            success=success,
            error=error,
        )
    finally:
        client.close()
        conn.close()


def run_all_template_variants(
    *,
    model_alias: str,
    scenario_file: Path,
    db_path: Path,
    mode: str = "baseline",
) -> RunBatchResult:
    model = get_model_config(model_alias)
    template = load_scenario_template(scenario_file)
    rendered_prompts = _build_rendered_prompts_for_template(
        template=template,
        mode=mode,
    )

    client = _build_client_from_env()
    conn = connect(DbConfig(path=db_path))

    success_count = 0
    failure_count = 0

    try:
        upsert_model(
            conn,
            id=model.alias,
            name=model.name,
            provider=model.provider,
            model_id=model.model_id,
        )

        upsert_scenario_record(
            conn,
            id=template.id,
            pillar=template.pillar,
            category=template.category,
            jurisdiction=template.jurisdiction,
            difficulty=template.difficulty,
        )

        config_snapshot = json.dumps(
            {
                "model_alias": model.alias,
                "provider_model_id": model.model_id,
                "scenario_file": str(scenario_file),
                "mode": mode,
                "variant_group": template.variant_group,
                "variant_count": len(rendered_prompts),
            }
        )

        run_id = create_benchmark_run(
            conn,
            model_id=model.alias,
            mode=mode,
            status="running",
            config_snapshot=config_snapshot,
        )

        for rendered in rendered_prompts:
            if mode == "adversarial" and template.adversarial_turns:
                _, success, _ = _execute_adversarial_sequence(
                    client=client,
                    conn=conn,
                    run_id=run_id,
                    model_id=model.model_id,
                    rendered=rendered,
                    adversarial_turns=template.adversarial_turns,
                    temperature=model.temperature,
                    max_tokens=_effective_max_tokens(
                        rendered.pillar, model.max_tokens
                    ),
                    top_p=model.top_p,
                    model=model,
                )
            else:
                provider_response = _execute_rendered_prompt(
                    client=client,
                    conn=conn,
                    run_id=run_id,
                    model_id=model.model_id,
                    rendered=rendered,
                    temperature=model.temperature,
                    max_tokens=_effective_max_tokens(
                        rendered.pillar, model.max_tokens
                    ),
                    top_p=model.top_p,
                    model=model,
                )
                success = provider_response.success

            if success:
                success_count += 1
            else:
                failure_count += 1

        if failure_count == 0:
            mark_benchmark_run_completed(conn, run_id=run_id)
        else:
            mark_benchmark_run_failed(conn, run_id=run_id)

        return RunBatchResult(
            run_id=run_id,
            model_alias=model.alias,
            scenario_id=template.id,
            mode=mode,
            total_count=len(rendered_prompts),
            success_count=success_count,
            failure_count=failure_count,
        )
    finally:
        client.close()
        conn.close()


def run_template_folder(
    *,
    model_alias: str,
    folder_path: Path,
    db_path: Path,
    mode: str = "baseline",
    seed: int | None = None,
    n_instances: int = 1,
    max_workers: int = 4,
    client_factory: Callable[[], OpenRouterClient] | None = None,
) -> RunFolderResult:
    model = get_model_config(model_alias)
    scenario_files = load_template_files(folder_path)

    factory = client_factory or _build_client_from_env
    conn = connect(DbConfig(path=db_path))

    success_count = 0
    failure_count = 0
    total_prompt_count = 0
    worker_errors: list[str] = []

    try:
        upsert_model(
            conn,
            id=model.alias,
            name=model.name,
            provider=model.provider,
            model_id=model.model_id,
        )

        config_snapshot = json.dumps(
            {
                "model_alias": model.alias,
                "provider_model_id": model.model_id,
                "folder_path": str(folder_path),
                "mode": mode,
                "scenario_file_count": len(scenario_files),
            }
        )

        run_id = create_benchmark_run(
            conn,
            model_id=model.alias,
            mode=mode,
            status="running",
            config_snapshot=config_snapshot,
        )

        # Write run manifest (Phase 5)
        scenario_hashes = sorted(
            hashlib.sha256(f.read_bytes()).hexdigest() for f in scenario_files
        )
        scenario_set_hash = hashlib.sha256(
            "\n".join(scenario_hashes).encode()
        ).hexdigest()[:16]
        scenario_version = (
            folder_path.parent.name
            if (folder_path.parent.name.startswith("v"))
            else "v1"
        )

        # Record the default seed when this run contains generated facts.
        if seed is None:
            for sf in scenario_files:
                try:
                    has_fact_space = (
                        load_scenario_template(sf).fact_space is not None
                    )
                except ScenarioTemplateLoadError:
                    continue
                if has_fact_space:
                    seed = 42
                    break

        # Compute generator_hash from all fact_space blocks when seeded.
        # Sorting makes this independent of filesystem/execution order.
        generator_hash: str | None = None
        if seed is not None:
            fact_space_blobs: list[str] = []
            for sf in scenario_files:
                try:
                    tmpl = load_scenario_template(sf)
                    if tmpl.fact_space is not None:
                        fact_space_blobs.append(
                            json.dumps(tmpl.fact_space, sort_keys=True)
                        )
                except Exception:
                    pass
            if fact_space_blobs:
                generator_hash = hashlib.sha256(
                    "\n".join(sorted(fact_space_blobs)).encode()
                ).hexdigest()[:16]

        upsert_run_manifest(
            conn,
            run_id=run_id,
            model_alias=model.alias,
            model_snapshot_json=json.dumps(
                {
                    "alias": model.alias,
                    "model_id": model.model_id,
                    "provider": model.provider,
                    "temperature": model.temperature,
                    "max_tokens": model.max_tokens,
                }
            ),
            scenario_set_version=scenario_version,
            scenario_set_hash=scenario_set_hash,
            seed=seed,
            timestamp=config_snapshot,
            generator_hash=generator_hash,
            n_instances=n_instances if seed is not None else None,
        )

        # Scenario-level work is dispatched to workers; ALL database writes
        # happen on this main thread as futures complete. ``max_workers <= 1``
        # reproduces the sequential path (same per-scenario work, same rows).
        if max_workers <= 1:
            client = factory()
            try:
                for scenario_file in scenario_files:
                    work = _process_scenario(
                        scenario_file=scenario_file,
                        model=model,
                        mode=mode,
                        seed=seed,
                        n_instances=n_instances,
                        client=client,
                    )
                    s, f = _persist_scenario(
                        conn=conn,
                        run_id=run_id,
                        work=work,
                        model=model,
                    )
                    success_count += s
                    failure_count += f
                    total_prompt_count += len(work.prompt_results)
            finally:
                client.close()
        else:

            def _worker(scenario_file: Path) -> _ScenarioWork:
                wclient = factory()
                try:
                    return _process_scenario(
                        scenario_file=scenario_file,
                        model=model,
                        mode=mode,
                        seed=seed,
                        n_instances=n_instances,
                        client=wclient,
                    )
                finally:
                    wclient.close()

            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                fut_to_file = {
                    ex.submit(_worker, sf): sf for sf in scenario_files
                }
                for fut in as_completed(fut_to_file):
                    sf = fut_to_file[fut]
                    try:
                        work = fut.result()
                    except Exception as exc:
                        worker_errors.append(f"{sf.name}: {exc!r}")
                        continue
                    s, f = _persist_scenario(
                        conn=conn,
                        run_id=run_id,
                        work=work,
                        model=model,
                    )
                    success_count += s
                    failure_count += f
                    total_prompt_count += len(work.prompt_results)

        if failure_count == 0 and not worker_errors:
            mark_benchmark_run_completed(conn, run_id=run_id)
        else:
            mark_benchmark_run_failed(conn, run_id=run_id)

        if worker_errors:
            raise RuntimeError(
                "Worker errors during run (other scenarios persisted): "
                + "; ".join(worker_errors)
            )

        return RunFolderResult(
            run_id=run_id,
            model_alias=model.alias,
            folder_path=str(folder_path),
            mode=mode,
            scenario_count=len(scenario_files),
            total_prompt_count=total_prompt_count,
            success_count=success_count,
            failure_count=failure_count,
        )
    finally:
        conn.close()


def _render_procedural(
    template: ScenarioTemplate,
    *,
    mode: str,
    seed: int,
    n_instances: int,
) -> list[RenderedPrompt]:
    """Render n_instances fact-space instances for a procedural template."""
    fact_space = parse_fact_space(template.fact_space)  # type: ignore[arg-type]
    rng = random.Random(seed_for(template.id, seed))
    rendered: list[RenderedPrompt] = []
    for i in range(n_instances):
        try:
            instance_vars = sample_instance(fact_space, rng=rng, draw_index=i)
        except FactGenerationError:
            break
        rp = render_prompt(
            template,
            variables=instance_vars,
            mode=mode,
            variant_id=f"inst{i}",
        )
        rendered.append(_dc_replace(rp, instance_vars=instance_vars))
    return rendered


def _build_rendered_prompts_for_template(
    *,
    template: ScenarioTemplate,
    mode: str,
) -> list[RenderedPrompt]:
    render_mode = mode if mode != "adversarial" else "baseline"

    if template.variant_group:
        return generate_prompts_for_template(
            template,
            mode=render_mode,
        )

    return [
        render_prompt(
            template,
            variables={},
            mode=render_mode,
            variant_id=None,
        )
    ]


def _process_scenario(
    *,
    scenario_file: Path,
    model,
    mode: str,
    seed: int | None,
    n_instances: int,
    client: OpenRouterClient,
) -> _ScenarioWork:
    """Worker entry point: render + call the model for one scenario file.

    Performs no database writes and uses only its own provider client, so
    it is safe to run inside a worker thread. Per-scenario seeding flows
    through ``seed_for(template.id, seed)``, which depends only on the
    template id and the run seed — never on execution order or thread
    identity — so the same file yields identical work anywhere it runs.
    """
    template = load_scenario_template(scenario_file)

    if template.fact_space is not None:
        render_mode = mode if mode != "adversarial" else "baseline"
        rendered_prompts = _render_procedural(
            template,
            mode=render_mode,
            seed=42 if seed is None else seed,
            n_instances=n_instances,
        )
    else:
        rendered_prompts = _build_rendered_prompts_for_template(
            template=template,
            mode=mode,
        )

    prompt_results: list[_PromptResult] = []
    for rendered in rendered_prompts:
        if mode == "adversarial" and template.adversarial_turns:
            turns, success, _ = _run_adversarial(
                client=client,
                model_id=model.model_id,
                rendered=rendered,
                adversarial_turns=template.adversarial_turns,
                temperature=model.temperature,
                max_tokens=_effective_max_tokens(
                    rendered.pillar, model.max_tokens
                ),
                top_p=model.top_p,
                model=model,
            )
        else:
            provider_response = client.chat(
                model_id=model.model_id,
                system_prompt=rendered.system_prompt,
                user_prompt=rendered.user_prompt,
                temperature=model.temperature,
                max_tokens=_effective_max_tokens(
                    rendered.pillar, model.max_tokens
                ),
                top_p=model.top_p,
                reasoning=_reasoning_param(model),
            )
            instance_json = (
                json.dumps(rendered.instance_vars)
                if rendered.instance_vars is not None
                else None
            )
            turns = [
                _TurnRecord(
                    scenario_id=rendered.scenario_id,
                    variant_id=rendered.variant_id,
                    mode=mode,
                    turn_number=1,
                    system_prompt_sent=rendered.system_prompt,
                    user_prompt_sent=rendered.user_prompt,
                    instance_json=instance_json,
                    response=provider_response,
                )
            ]
            success = provider_response.success

        prompt_results.append(_PromptResult(turns=turns, success=success))

    return _ScenarioWork(
        template_id=template.id,
        pillar=template.pillar,
        category=template.category,
        jurisdiction=template.jurisdiction,
        difficulty=template.difficulty,
        prompt_results=prompt_results,
    )


def _persist_scenario(
    *,
    conn,
    run_id: str,
    work: _ScenarioWork,
    model,
) -> tuple[int, int]:
    """Main-thread: write one scenario's rows to the database.

    Returns ``(success_count, failure_count)`` at the rendered-prompt
    level — one prompt counts as one success or one failure, even when
    it spanned several adversarial turns. Must be called only from the
    main thread so a single sqlite connection is never shared across
    threads.
    """
    upsert_scenario_record(
        conn,
        id=work.template_id,
        pillar=work.pillar,
        category=work.category,
        jurisdiction=work.jurisdiction,
        difficulty=work.difficulty,
    )

    success_count = 0
    failure_count = 0
    for pr in work.prompt_results:
        for t in pr.turns:
            insert_response(
                conn,
                run_id=run_id,
                scenario_id=t.scenario_id,
                variant_id=t.variant_id,
                mode=t.mode,
                turn_number=t.turn_number,
                system_prompt_sent=t.system_prompt_sent,
                user_prompt_sent=t.user_prompt_sent,
                raw_response=t.response.text if t.response.success else None,
                latency_ms=t.response.latency_ms,
                instance_json=t.instance_json,
                **_usage_kwargs(t.response, model),
            )
        if pr.success:
            success_count += 1
        else:
            failure_count += 1

    return success_count, failure_count


def _execute_rendered_prompt(
    *,
    client: OpenRouterClient,
    conn,
    run_id: str,
    model_id: str,
    rendered: RenderedPrompt,
    temperature: float,
    max_tokens: int,
    top_p: float,
    model,
):
    provider_response = client.chat(
        model_id=model_id,
        system_prompt=rendered.system_prompt,
        user_prompt=rendered.user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        reasoning=_reasoning_param(model),
    )

    insert_response(
        conn,
        run_id=run_id,
        scenario_id=rendered.scenario_id,
        variant_id=rendered.variant_id,
        mode=rendered.mode,
        turn_number=1,
        system_prompt_sent=rendered.system_prompt,
        user_prompt_sent=rendered.user_prompt,
        raw_response=provider_response.text
        if provider_response.success
        else None,
        latency_ms=provider_response.latency_ms,
        instance_json=json.dumps(rendered.instance_vars)
        if rendered.instance_vars is not None
        else None,
        **_usage_kwargs(provider_response, model),
    )

    return provider_response


def _run_adversarial(
    *,
    client: OpenRouterClient,
    model_id: str,
    rendered: RenderedPrompt,
    adversarial_turns,
    temperature: float,
    max_tokens: int,
    top_p: float,
    model,
) -> tuple[list[_TurnRecord], bool, str | None]:
    """Run the adversarial multi-turn API sequence without DB writes.

    Returns ``(turn_records, success, error)``. Each record carries the
    provider response for one turn; the caller is responsible for
    persisting them (from the main thread). ``instance_json`` is left
    ``None`` to match the historical adversarial insert shape.
    """
    messages = [
        ChatMessage(role="system", content=rendered.system_prompt),
        ChatMessage(role="user", content=rendered.user_prompt),
    ]

    turns: list[_TurnRecord] = []

    first_response = client.chat_messages(
        model_id=model_id,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        reasoning=_reasoning_param(model),
    )

    turns.append(
        _TurnRecord(
            scenario_id=rendered.scenario_id,
            variant_id=rendered.variant_id,
            mode="adversarial",
            turn_number=1,
            system_prompt_sent=rendered.system_prompt,
            user_prompt_sent=rendered.user_prompt,
            instance_json=json.dumps(rendered.instance_vars)
            if rendered.instance_vars is not None
            else None,
            response=first_response,
        )
    )

    if not first_response.success:
        return turns, False, first_response.error

    messages.append(ChatMessage(role="assistant", content=first_response.text))

    turn_number = 2
    for turn in adversarial_turns:
        messages.append(ChatMessage(role="user", content=turn.user_prompt))

        response = client.chat_messages(
            model_id=model_id,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            reasoning=_reasoning_param(model),
        )

        turns.append(
            _TurnRecord(
                scenario_id=rendered.scenario_id,
                variant_id=rendered.variant_id,
                mode="adversarial",
                turn_number=turn_number,
                system_prompt_sent=rendered.system_prompt,
                user_prompt_sent=turn.user_prompt,
                instance_json=json.dumps(rendered.instance_vars)
                if rendered.instance_vars is not None
                else None,
                response=response,
            )
        )

        if not response.success:
            return turns, False, response.error

        messages.append(ChatMessage(role="assistant", content=response.text))
        turn_number += 1

    return turns, True, None


def _execute_adversarial_sequence(
    *,
    client: OpenRouterClient,
    conn,
    run_id: str,
    model_id: str,
    rendered: RenderedPrompt,
    adversarial_turns,
    temperature: float,
    max_tokens: int,
    top_p: float,
    model,
) -> tuple[list[str], bool, str | None]:
    turns, success, error = _run_adversarial(
        client=client,
        model_id=model_id,
        rendered=rendered,
        adversarial_turns=adversarial_turns,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        model=model,
    )
    response_ids: list[str] = []
    for t in turns:
        response_ids.append(
            insert_response(
                conn,
                run_id=run_id,
                scenario_id=t.scenario_id,
                variant_id=t.variant_id,
                mode=t.mode,
                turn_number=t.turn_number,
                system_prompt_sent=t.system_prompt_sent,
                user_prompt_sent=t.user_prompt_sent,
                raw_response=t.response.text if t.response.success else None,
                latency_ms=t.response.latency_ms,
                **_usage_kwargs(t.response, model),
            )
        )
    return response_ids, success, error


def _build_client_from_env() -> OpenRouterClient:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Add it to your .env file."
        )

    base_url = os.getenv(
        "OPENROUTER_BASE_URL",
        "https://openrouter.ai/api/v1",
    )
    app_name = os.getenv("OPENROUTER_APP_NAME", "IRBG")
    site_url = os.getenv("OPENROUTER_SITE_URL")

    return OpenRouterClient(
        api_key=api_key,
        base_url=base_url,
        app_name=app_name,
        site_url=site_url,
    )
