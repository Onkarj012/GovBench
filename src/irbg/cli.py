from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from irbg.analysis.aggregate import (
    AggregateScoreError,
    aggregate_run_score,
)
from irbg.analysis.compare import compare_runs
from irbg.analysis.export import write_leaderboard
from irbg.analysis.quality import (
    DEFAULT_INVALID_THRESHOLD,
    assess_all_runs,
)
from irbg.analysis.reporting import (
    RunReportError,
    build_run_report,
    write_run_report_json,
    write_run_report_markdown,
)
from irbg.analysis.visualize import (
    VisualizationError,
    generate_latency_chart,
    generate_run_summary_chart,
)
from irbg.config import ConfigError, load_models_config
from irbg.db.operations import DbConfig, connect, list_benchmark_runs
from irbg.db.schema import create_tables
from irbg.demographics import DemographicsError, get_variant_group
from irbg.engine.prompt_builder import PromptBuildError
from irbg.engine.provider import OpenRouterClient
from irbg.engine.runner import (
    run_all_template_variants,
    run_single_scenario,
    run_single_template_variant,
    run_template_folder,
)
from irbg.engine.variant_generator import (
    VariantGenerationError,
    generate_single_prompt_for_variant,
)
from irbg.scenarios.discovery import ScenarioDiscoveryError
from irbg.scenarios.template_loader import (
    ScenarioTemplateLoadError,
    load_scenario_template,
)
from irbg.scoring.p1 import P1ScoringError, score_p1_run
from irbg.scoring.p2 import P2ScoringError, score_p2_run
from irbg.scoring.p3 import P3ScoringError, score_p3_run
from irbg.scoring.p4 import P4ScoringError, score_p4_run
from irbg.scoring.p5 import P5ScoringError, score_p5_run
from irbg.scoring.p6 import P6ScoringError, score_p6_run

console = Console()


@click.group()
def main() -> None:
    load_dotenv()


def _ensure_database(db_path: Path) -> None:
    db = DbConfig(path=db_path)
    conn = connect(db)
    try:
        create_tables(conn)
    finally:
        conn.close()


@main.command("init-db")
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
def init_db(db_path: Path) -> None:
    _ensure_database(db_path)
    console.print(
        f"[green]OK[/green] Database initialized at: {db_path.resolve()}"
    )


@main.command("list-models")
def list_models() -> None:
    try:
        models = load_models_config()
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc

    table = Table(title="Configured Models")
    table.add_column("Alias")
    table.add_column("Name")
    table.add_column("Provider")
    table.add_column("OpenRouter Model ID")

    for model in models.values():
        table.add_row(
            model.alias,
            model.name,
            model.provider,
            model.model_id,
        )

    console.print(table)


@main.command("list-runs")
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
def list_runs(db_path: Path) -> None:
    _ensure_database(db_path)

    conn = connect(DbConfig(path=db_path))
    try:
        rows = list_benchmark_runs(conn)
    finally:
        conn.close()

    table = Table(title="Benchmark Runs")
    table.add_column("Run ID")
    table.add_column("Model")
    table.add_column("Mode")
    table.add_column("Status")
    table.add_column("Started At")
    table.add_column("Completed At")

    for row in rows:
        table.add_row(
            str(row["id"]),
            str(row["model_id"]),
            str(row["mode"]),
            str(row["status"]),
            str(row["started_at"]),
            str(row["completed_at"] or "-"),
        )

    console.print(table)


@main.command("quarantine-check")
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
@click.option(
    "--threshold",
    type=float,
    default=DEFAULT_INVALID_THRESHOLD,
    show_default=True,
    help="Max share of empty/invalid responses before a run is quarantined.",
)
def quarantine_check_cmd(db_path: Path, threshold: float) -> None:
    """Flag runs with too many empty/invalid responses."""
    _ensure_database(db_path)
    reports = assess_all_runs(db_path=db_path, threshold=threshold)

    table = Table(title="Run Quality / Quarantine")
    table.add_column("Run ID")
    table.add_column("Model")
    table.add_column("Invalid", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Invalid %", justify="right")
    table.add_column("Status")

    flagged = 0
    for report in sorted(reports, key=lambda r: r.invalid_ratio, reverse=True):
        if report.quarantined:
            flagged += 1
        table.add_row(
            report.run_id[:8],
            report.model_alias,
            str(report.invalid),
            str(report.total),
            f"{report.invalid_ratio * 100:.1f}%",
            "[red]QUARANTINE[/red]"
            if report.quarantined
            else "[green]ok[/green]",
        )

    console.print(table)
    console.print(f"{flagged} run(s) quarantined at threshold {threshold:.0%}.")


@main.command("export-leaderboard")
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=Path("./frontend/lib/leaderboard.json"),
    show_default=True,
)
@click.option(
    "--threshold",
    type=float,
    default=DEFAULT_INVALID_THRESHOLD,
    show_default=True,
    help="Exclude runs above this share of empty/invalid responses.",
)
def export_leaderboard_cmd(db_path: Path, out: Path, threshold: float) -> None:
    """Generate the frontend leaderboard JSON from the DB (source of truth)."""
    _ensure_database(db_path)
    count = write_leaderboard(
        db_path=db_path, output_path=out, threshold=threshold
    )
    console.print(
        f"[green]OK[/green] Exported {count} model(s) to {out} "
        f"(quarantine threshold {threshold:.0%})."
    )


@main.command("list-variants")
@click.option("--group", "group_name", required=True)
def list_variants(group_name: str) -> None:
    try:
        variants = get_variant_group(group_name)
    except DemographicsError as exc:
        raise click.ClickException(str(exc)) from exc

    table = Table(title=f"Variants: {group_name}")
    table.add_column("Variant ID")
    table.add_column("Name")
    table.add_column("Gender")
    table.add_column("Nationality")
    table.add_column("Religion")

    for variant in variants:
        table.add_row(
            variant.id,
            variant.name,
            variant.gender,
            variant.nationality,
            variant.religion,
        )

    console.print(table)


@main.command("ping-openrouter")
@click.option("--model", "model_alias", required=True)
@click.option(
    "--message",
    default="Reply with exactly one word: pong",
    show_default=True,
)
def ping_openrouter(model_alias: str, message: str) -> None:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise click.ClickException("OPENROUTER_API_KEY is not set.")

    try:
        model = load_models_config()[model_alias]
    except KeyError as exc:
        raise click.ClickException(
            f"Unknown model alias: {model_alias}"
        ) from exc
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc

    client = OpenRouterClient(
        api_key=api_key,
        base_url=os.getenv(
            "OPENROUTER_BASE_URL",
            "https://openrouter.ai/api/v1",
        ),
        app_name=os.getenv("OPENROUTER_APP_NAME", "IRBG"),
        site_url=os.getenv("OPENROUTER_SITE_URL"),
    )

    try:
        response = client.chat(
            model_id=model.model_id,
            system_prompt="You are a concise assistant.",
            user_prompt=message,
            temperature=model.temperature,
            max_tokens=model.max_tokens,
        )
    finally:
        client.close()

    if not response.success:
        raise click.ClickException(response.error or "Provider error")

    console.print("[green]OpenRouter ping successful[/green]")
    console.print(f"Model: {model.name}")
    console.print(f"Latency: {response.latency_ms} ms")
    console.print(f"Tokens: {response.total_tokens}")
    console.print(f"Response: {response.text}")


@main.command("render-template")
@click.option(
    "--scenario-file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
)
@click.option("--variant-id", required=True)
@click.option("--mode", default="baseline", show_default=True)
def render_template(
    scenario_file: Path,
    variant_id: str,
    mode: str,
) -> None:
    try:
        template = load_scenario_template(scenario_file)
        rendered = generate_single_prompt_for_variant(
            template,
            variant_id=variant_id,
            mode=mode,
        )
    except (
        ScenarioTemplateLoadError,
        VariantGenerationError,
        DemographicsError,
        PromptBuildError,
    ) as exc:
        raise click.ClickException(str(exc)) from exc

    metadata = Table(show_header=False, box=None)
    metadata.add_row("Scenario ID", rendered.scenario_id)
    metadata.add_row("Variant ID", rendered.variant_id or "-")
    metadata.add_row("Mode", rendered.mode)
    metadata.add_row("Jurisdiction", rendered.jurisdiction or "-")
    metadata.add_row("Category", rendered.category)

    console.print(Panel.fit(metadata, title="Rendered Prompt Metadata"))
    console.print(Panel(rendered.system_prompt, title="System Prompt"))
    console.print(Panel(rendered.user_prompt, title="User Prompt"))


@main.command("run-once")
@click.option("--model", "model_alias", required=True)
@click.option(
    "--scenario-file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
@click.option("--mode", default="baseline", show_default=True)
def run_once(
    model_alias: str,
    scenario_file: Path,
    db_path: Path,
    mode: str,
) -> None:
    _ensure_database(db_path)

    try:
        result = run_single_scenario(
            model_alias=model_alias,
            scenario_file=scenario_file,
            db_path=db_path,
            mode=mode,
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    if not result.success:
        raise click.ClickException(result.error or "Run failed")

    console.print("[green]Scenario run completed successfully[/green]")
    console.print(f"Run ID: {result.run_id}")
    console.print(f"Response ID: {result.response_id}")
    console.print(f"Model Alias: {result.model_alias}")
    console.print(f"Scenario ID: {result.scenario_id}")


@main.command("run-template-variant")
@click.option("--model", "model_alias", required=True)
@click.option(
    "--scenario-file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
)
@click.option("--variant-id", required=True)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
@click.option("--mode", default="baseline", show_default=True)
def run_template_variant(
    model_alias: str,
    scenario_file: Path,
    variant_id: str,
    db_path: Path,
    mode: str,
) -> None:
    _ensure_database(db_path)

    try:
        result = run_single_template_variant(
            model_alias=model_alias,
            scenario_file=scenario_file,
            variant_id=variant_id,
            db_path=db_path,
            mode=mode,
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    if not result.success:
        raise click.ClickException(result.error or "Run failed")

    console.print("[green]Template variant run completed[/green]")
    console.print(f"Run ID: {result.run_id}")
    console.print(f"Response ID: {result.response_id}")
    console.print(f"Model Alias: {result.model_alias}")
    console.print(f"Scenario ID: {result.scenario_id}")


@main.command("run-template-group")
@click.option("--model", "model_alias", required=True)
@click.option(
    "--scenario-file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
@click.option("--mode", default="baseline", show_default=True)
def run_template_group(
    model_alias: str,
    scenario_file: Path,
    db_path: Path,
    mode: str,
) -> None:
    _ensure_database(db_path)

    try:
        result = run_all_template_variants(
            model_alias=model_alias,
            scenario_file=scenario_file,
            db_path=db_path,
            mode=mode,
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    console.print("[green]Template group run finished[/green]")
    console.print(f"Run ID: {result.run_id}")
    console.print(f"Model Alias: {result.model_alias}")
    console.print(f"Scenario ID: {result.scenario_id}")
    console.print(f"Mode: {result.mode}")
    console.print(f"Total: {result.total_count}")
    console.print(f"Succeeded: {result.success_count}")
    console.print(f"Failed: {result.failure_count}")


@main.command("run-template-folder")
@click.option("--model", "model_alias", required=True)
@click.option(
    "--scenario-folder",
    type=click.Path(exists=True, path_type=Path),
    required=True,
)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
@click.option("--mode", default="baseline", show_default=True)
@click.option(
    "--repeats",
    type=click.IntRange(min=1),
    default=1,
    show_default=True,
    help="Samples per item (k-repeat) for variance/CI estimation.",
)
def run_template_folder_cmd(
    model_alias: str,
    scenario_folder: Path,
    db_path: Path,
    mode: str,
    repeats: int,
) -> None:
    _ensure_database(db_path)

    try:
        result = run_template_folder(
            model_alias=model_alias,
            folder_path=scenario_folder,
            db_path=db_path,
            mode=mode,
            repeats=repeats,
        )
    except (
        ConfigError,
        RuntimeError,
        ScenarioDiscoveryError,
        ScenarioTemplateLoadError,
        VariantGenerationError,
        DemographicsError,
        PromptBuildError,
        ValueError,
    ) as exc:
        raise click.ClickException(str(exc)) from exc

    console.print("[green]Template folder run finished[/green]")
    console.print(f"Run ID: {result.run_id}")
    console.print(f"Model Alias: {result.model_alias}")
    console.print(f"Folder: {result.folder_path}")
    console.print(f"Mode: {result.mode}")
    console.print(f"Scenarios: {result.scenario_count}")
    console.print(f"Total Prompt Count: {result.total_prompt_count}")
    console.print(f"Succeeded: {result.success_count}")
    console.print(f"Failed: {result.failure_count}")


@main.command("score-p1-run")
@click.option("--run-id", required=True)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=None,
)
def score_p1_run_cmd(
    run_id: str,
    db_path: Path,
    output: Path | None,
) -> None:
    _ensure_database(db_path)

    try:
        result = score_p1_run(
            db_path=db_path,
            run_id=run_id,
        )
    except P1ScoringError as exc:
        raise click.ClickException(str(exc)) from exc

    summary = Table(title="P1 Run Score")
    summary.add_column("Field")
    summary.add_column("Value")
    summary.add_row("Run ID", result.run_id)
    summary.add_row("Model", result.model_alias)
    summary.add_row("Mode", result.mode)
    summary.add_row("Scenario Count", str(result.scenario_count))
    summary.add_row("Overall Score", f"{result.overall_score:.2f}")
    console.print(summary)

    detail = Table(title="Scenario Breakdown")
    detail.add_column("Scenario ID")
    detail.add_column("Category")
    detail.add_column("Decision")
    detail.add_column("Parity Gap")
    detail.add_column("Length")
    detail.add_column("Sentiment")
    detail.add_column("Total")
    detail.add_column("Majority")
    detail.add_column("Outliers")

    for item in result.scenarios:
        outliers = ", ".join(item.outlier_variants) or "-"
        detail.add_row(
            item.scenario_id,
            item.category,
            f"{item.decision_score:.2f}",
            f"{item.parity_gap:.2f}",
            f"{item.length_score:.2f}",
            f"{item.sentiment_score:.2f}",
            f"{item.total_score:.2f}",
            item.majority_decision,
            outliers,
        )

    console.print(detail)

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(asdict(result), indent=2))
        console.print(f"Saved JSON score report to {output.resolve()}")


@main.command("score-p2-run")
@click.option("--run-id", required=True)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=None,
)
def score_p2_run_cmd(
    run_id: str,
    db_path: Path,
    output: Path | None,
) -> None:
    _ensure_database(db_path)

    try:
        result = score_p2_run(
            db_path=db_path,
            run_id=run_id,
        )
    except P2ScoringError as exc:
        raise click.ClickException(str(exc)) from exc

    summary = Table(title="P2 Run Score (Procedural Integrity)")
    summary.add_column("Field")
    summary.add_column("Value")
    summary.add_row("Run ID", result.run_id)
    summary.add_row("Model", result.model_alias)
    summary.add_row("Mode", result.mode)
    summary.add_row("Scenario Count", str(result.scenario_count))
    summary.add_row("Overall Score", f"{result.overall_score:.2f}")
    console.print(summary)

    detail = Table(title="Scenario Breakdown")
    detail.add_column("Scenario ID")
    detail.add_column("Category")
    detail.add_column("Score")
    detail.add_column("Flags")

    for item in result.scenarios:
        detail.add_row(
            item.scenario_id,
            item.category,
            f"{item.score:.2f}",
            ", ".join(item.judge_flags) if item.judge_flags else "-",
        )

    console.print(detail)

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(asdict(result), indent=2))
        console.print(f"Saved JSON score report to {output.resolve()}")


@main.command("score-p3-run")
@click.option("--run-id", required=True)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=None,
)
def score_p3_run_cmd(
    run_id: str,
    db_path: Path,
    output: Path | None,
) -> None:
    _ensure_database(db_path)

    try:
        result = score_p3_run(
            db_path=db_path,
            run_id=run_id,
        )
    except P3ScoringError as exc:
        raise click.ClickException(str(exc)) from exc

    summary = Table(title="P3 Run Score (Corruption Resistance)")
    summary.add_column("Field")
    summary.add_column("Value")
    summary.add_row("Run ID", result.run_id)
    summary.add_row("Model", result.model_alias)
    summary.add_row("Mode", result.mode)
    summary.add_row("Scenario Count", str(result.scenario_count))
    summary.add_row("Overall Score", f"{result.overall_score:.2f}")
    console.print(summary)

    detail = Table(title="Scenario Breakdown")
    detail.add_column("Scenario ID")
    detail.add_column("Category")
    detail.add_column("Score")
    detail.add_column("Flags")

    for item in result.scenarios:
        detail.add_row(
            item.scenario_id,
            item.category,
            f"{item.score:.2f}",
            ", ".join(item.judge_flags) if item.judge_flags else "-",
        )

    console.print(detail)

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(asdict(result), indent=2))
        console.print(f"Saved JSON score report to {output.resolve()}")


@main.command("score-p4-run")
@click.option("--run-id", required=True)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=None,
)
def score_p4_run_cmd(
    run_id: str,
    db_path: Path,
    output: Path | None,
) -> None:
    _ensure_database(db_path)

    try:
        result = score_p4_run(
            db_path=db_path,
            run_id=run_id,
        )
    except P4ScoringError as exc:
        raise click.ClickException(str(exc)) from exc

    summary = Table(title="P4 Run Score (Jurisdictional Awareness)")
    summary.add_column("Field")
    summary.add_column("Value")
    summary.add_row("Run ID", result.run_id)
    summary.add_row("Model", result.model_alias)
    summary.add_row("Mode", result.mode)
    summary.add_row("Scenario Count", str(result.scenario_count))
    summary.add_row("Overall Score", f"{result.overall_score:.2f}")
    console.print(summary)

    detail = Table(title="Scenario Breakdown")
    detail.add_column("Scenario ID")
    detail.add_column("Category")
    detail.add_column("Score")
    detail.add_column("Flags")

    for item in result.scenarios:
        detail.add_row(
            item.scenario_id,
            item.category,
            f"{item.score:.2f}",
            ", ".join(item.judge_flags) if item.judge_flags else "-",
        )

    console.print(detail)

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(asdict(result), indent=2))
        console.print(f"Saved JSON score report to {output.resolve()}")


@main.command("score-p5-run")
@click.option("--run-id", required=True)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=None,
)
def score_p5_run_cmd(
    run_id: str,
    db_path: Path,
    output: Path | None,
) -> None:
    _ensure_database(db_path)

    try:
        result = score_p5_run(
            db_path=db_path,
            run_id=run_id,
        )
    except P5ScoringError as exc:
        raise click.ClickException(str(exc)) from exc

    summary = Table(title="P5 Run Score (Transparency & Explainability)")
    summary.add_column("Field")
    summary.add_column("Value")
    summary.add_row("Run ID", result.run_id)
    summary.add_row("Model", result.model_alias)
    summary.add_row("Mode", result.mode)
    summary.add_row("Scenario Count", str(result.scenario_count))
    summary.add_row("Overall Score", f"{result.overall_score:.2f}")
    console.print(summary)

    detail = Table(title="Scenario Breakdown")
    detail.add_column("Scenario ID")
    detail.add_column("Category")
    detail.add_column("Score")
    detail.add_column("Flags")

    for item in result.scenarios:
        detail.add_row(
            item.scenario_id,
            item.category,
            f"{item.score:.2f}",
            ", ".join(item.judge_flags) if item.judge_flags else "-",
        )

    console.print(detail)

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(asdict(result), indent=2))
        console.print(f"Saved JSON score report to {output.resolve()}")


@main.command("score-p6-run")
@click.option("--run-id", required=True)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=None,
)
def score_p6_run_cmd(
    run_id: str,
    db_path: Path,
    output: Path | None,
) -> None:
    _ensure_database(db_path)

    try:
        result = score_p6_run(
            db_path=db_path,
            run_id=run_id,
        )
    except P6ScoringError as exc:
        raise click.ClickException(str(exc)) from exc

    summary = Table(title="P6 Run Score (Minority Protection)")
    summary.add_column("Field")
    summary.add_column("Value")
    summary.add_row("Run ID", result.run_id)
    summary.add_row("Model", result.model_alias)
    summary.add_row("Mode", result.mode)
    summary.add_row("Scenario Count", str(result.scenario_count))
    summary.add_row("Overall Score", f"{result.overall_score:.2f}")
    console.print(summary)

    detail = Table(title="Scenario Breakdown")
    detail.add_column("Scenario ID")
    detail.add_column("Category")
    detail.add_column("Score")
    detail.add_column("Flags")

    for item in result.scenarios:
        detail.add_row(
            item.scenario_id,
            item.category,
            f"{item.score:.2f}",
            ", ".join(item.judge_flags) if item.judge_flags else "-",
        )

    console.print(detail)

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(asdict(result), indent=2))
        console.print(f"Saved JSON score report to {output.resolve()}")


@main.command("aggregate-run")
@click.option("--run-id", required=True)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
def aggregate_run_cmd(
    run_id: str,
    db_path: Path,
) -> None:
    _ensure_database(db_path)

    try:
        result = aggregate_run_score(db_path=db_path, run_id=run_id)
    except AggregateScoreError as exc:
        raise click.ClickException(str(exc)) from exc

    table = Table(title="Aggregated IRBG Score")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Run ID", result.run_id)
    table.add_row("Model", result.model_alias)
    table.add_row("Mode", result.mode)
    table.add_row("Composite Score", f"{result.composite_score:.2f}")
    table.add_row("Grade", result.grade)
    table.add_row("Complete", "yes" if result.complete else "no (partial)")

    for pillar, score in sorted(result.pillar_scores.items()):
        table.add_row(pillar, f"{score:.2f}")

    console.print(table)


@main.command("calibrate-judge")
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
@click.option(
    "--calibration-path",
    type=click.Path(path_type=Path),
    default=None,
)
def calibrate_judge_cmd(
    db_path: Path,
    calibration_path: Path | None,
) -> None:
    from irbg.scoring.calibration import CalibrationError, calibrate_judges

    _ensure_database(db_path)

    try:
        report = calibrate_judges(
            calibration_path=calibration_path,
            db_path=db_path,
        )
    except CalibrationError as exc:
        raise click.ClickException(str(exc)) from exc

    summary = Table(title="Judge Calibration")
    summary.add_column("Metric")
    summary.add_column("Value")
    summary.add_row("Calibration Items", str(report.n))
    summary.add_row("Cohen's Kappa (vs gold)", f"{report.cohens_kappa:.4f}")
    summary.add_row("Mean Abs Error", f"{report.mean_abs_error:.2f}")
    console.print(summary)

    detail = Table(title="Per-Item Agreement")
    detail.add_column("ID")
    detail.add_column("Pillar")
    detail.add_column("Gold")
    detail.add_column("Judge")
    detail.add_column("Match")
    for item in report.items:
        match = "yes" if item.gold_bin == item.judge_bin else "no"
        detail.add_row(
            item.id,
            item.pillar,
            f"{item.gold_score:.0f}",
            f"{item.judge_score:.0f}",
            match,
        )
    console.print(detail)


@main.command("show-run")
@click.option("--run-id", required=True)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
def show_run_cmd(
    run_id: str,
    db_path: Path,
) -> None:
    _ensure_database(db_path)

    try:
        report = build_run_report(db_path=db_path, run_id=run_id)
    except RunReportError as exc:
        raise click.ClickException(str(exc)) from exc

    table = Table(title="Run Summary")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Run ID", report.run_id)
    table.add_row("Model", report.model_alias)
    table.add_row("Mode", report.mode)
    table.add_row("Status", report.status)
    table.add_row("Response Count", str(report.response_count))
    table.add_row("Scenario Count", str(report.scenario_count))
    table.add_row(
        "Average Latency (ms)",
        f"{report.average_latency_ms:.2f}",
    )
    table.add_row("Average Tokens", f"{report.average_tokens:.2f}")
    table.add_row(
        "Composite Score",
        str(report.composite_score)
        if report.composite_score is not None
        else "-",
    )
    table.add_row("Grade", report.grade or "-")

    console.print(table)

    if report.pillar_scores:
        pillar_table = Table(title="Pillar Scores")
        pillar_table.add_column("Pillar")
        pillar_table.add_column("Score")
        for pillar, score in sorted(report.pillar_scores.items()):
            pillar_table.add_row(pillar, f"{score:.2f}")
        console.print(pillar_table)


@main.command("report-run")
@click.option("--run-id", required=True)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=Path("./reports"),
    show_default=True,
)
def report_run_cmd(
    run_id: str,
    db_path: Path,
    output_dir: Path,
) -> None:
    _ensure_database(db_path)

    try:
        report = build_run_report(db_path=db_path, run_id=run_id)
    except RunReportError as exc:
        raise click.ClickException(str(exc)) from exc

    json_path = output_dir / f"{run_id}_report.json"
    md_path = output_dir / f"{run_id}_report.md"
    pillar_chart_path = output_dir / f"{run_id}_pillar_scores.png"
    latency_chart_path = output_dir / f"{run_id}_latency.png"

    write_run_report_json(report=report, output_path=json_path)
    write_run_report_markdown(report=report, output_path=md_path)

    try:
        generate_run_summary_chart(
            db_path=db_path,
            run_id=run_id,
            output_path=pillar_chart_path,
        )
    except VisualizationError as exc:
        console.print(f"[yellow]Chart skipped:[/yellow] {exc}")

    try:
        generate_latency_chart(
            db_path=db_path,
            run_id=run_id,
            output_path=latency_chart_path,
        )
    except VisualizationError as exc:
        console.print(f"[yellow]Chart skipped:[/yellow] {exc}")

    console.print("[green]Run report generated[/green]")
    console.print(f"JSON: {json_path.resolve()}")
    console.print(f"Markdown: {md_path.resolve()}")
    console.print(f"Pillar chart: {pillar_chart_path.resolve()}")
    console.print(f"Latency chart: {latency_chart_path.resolve()}")


@main.command("compare-runs")
@click.option("--left-run-id", required=True)
@click.option("--right-run-id", required=True)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
def compare_runs_cmd(
    left_run_id: str,
    right_run_id: str,
    db_path: Path,
) -> None:
    _ensure_database(db_path)

    comparison = compare_runs(
        db_path=db_path,
        left_run_id=left_run_id,
        right_run_id=right_run_id,
    )

    table = Table(title="Run Comparison")
    table.add_column("Field")
    table.add_column("Left")
    table.add_column("Right")

    table.add_row("Run ID", comparison.left_run_id, comparison.right_run_id)
    table.add_row("Model", comparison.left_model, comparison.right_model)
    table.add_row(
        "Composite Score",
        str(comparison.left_score),
        str(comparison.right_score),
    )
    table.add_row(
        "Grade",
        str(comparison.left_grade),
        str(comparison.right_grade),
    )

    console.print(table)

    delta_text = (
        str(comparison.score_delta)
        if comparison.score_delta is not None
        else "N/A"
    )
    console.print(f"Score delta (left - right): {delta_text}")

    if not comparison.scenario_set_match:
        console.print(
            "[yellow]WARNING:[/] scenario sets differ "
            f"(left={comparison.left_scenario_set_hash}, "
            f"right={comparison.right_scenario_set_hash}); "
            "per-scenario diff is not apples-to-apples."
        )

    if comparison.scenario_deltas:
        order = [
            "regressed",
            "newly_failing",
            "improved",
            "unchanged",
            "added",
            "removed",
        ]
        summary_text = ", ".join(
            f"{k}={comparison.summary[k]}"
            for k in order
            if k in comparison.summary
        )
        console.print(
            "Per-scenario diff (left=baseline -> right=candidate): "
            f"{summary_text}"
        )
        if comparison.regressed_scenarios:
            console.print(
                "[red]Regressed scenarios:[/] "
                + ", ".join(comparison.regressed_scenarios)
            )


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# Phase 3 + 4 commands
# ---------------------------------------------------------------------------


@main.command("canary-check")
@click.option(
    "--scenario-folder",
    type=click.Path(path_type=Path),
    required=True,
)
def canary_check_cmd(scenario_folder: Path) -> None:
    """Verify every scenario template in a folder has a canary string."""
    from irbg.scenarios.discovery import (
        ScenarioDiscoveryError,
        load_template_files,
    )
    from irbg.scenarios.template_loader import load_scenario_template

    try:
        files = load_template_files(scenario_folder)
    except ScenarioDiscoveryError as exc:
        raise click.ClickException(str(exc)) from exc

    table = Table(title="Canary Check")
    table.add_column("File")
    table.add_column("ID")
    table.add_column("Version")
    table.add_column("Canary")
    table.add_column("OK")

    all_ok = True
    for f in files:
        t = load_scenario_template(f)
        ok = bool(t.canary)
        if not ok:
            all_ok = False
        table.add_row(
            f.name,
            t.id,
            t.version,
            t.canary or "[red]MISSING[/red]",
            "[green]yes[/green]" if ok else "[red]no[/red]",
        )

    console.print(table)
    if not all_ok:
        raise click.ClickException(
            "One or more scenarios are missing a canary string."
        )
    console.print("[green]All canaries present.[/green]")


@main.command("compute-ci")
@click.option("--model", "model_alias", required=True)
@click.option("--mode", default="baseline", show_default=True)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
def compute_ci_cmd(model_alias: str, mode: str, db_path: Path) -> None:
    """Bootstrap 95% CI per pillar and composite for a model+mode."""
    from irbg.analysis.stats import StatsError, compute_model_ci

    _ensure_database(db_path)
    try:
        result = compute_model_ci(
            db_path=db_path, model_alias=model_alias, mode=mode
        )
    except StatsError as exc:
        raise click.ClickException(str(exc)) from exc

    table = Table(title=f"95% CI — {model_alias} / {mode}")
    table.add_column("Pillar")
    table.add_column("N")
    table.add_column("Mean")
    table.add_column("CI Low")
    table.add_column("CI High")
    for p in result.pillars:
        table.add_row(
            p.pillar,
            str(p.n),
            f"{p.mean:.2f}",
            f"{p.ci_low:.2f}",
            f"{p.ci_high:.2f}",
        )
    table.add_row(
        "COMPOSITE",
        "-",
        f"{result.composite_mean:.2f}",
        f"{result.composite_ci_low:.2f}",
        f"{result.composite_ci_high:.2f}",
    )
    console.print(table)


@main.command("robustness-delta")
@click.option("--model", "model_alias", required=True)
@click.option(
    "--mode",
    default="pressure",
    show_default=True,
    help="Mode to compare against baseline (pressure or adversarial).",
)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
def robustness_delta_cmd(model_alias: str, mode: str, db_path: Path) -> None:
    """Compute baseline − <mode> per pillar (positive = degraded)."""
    from irbg.analysis.stats import StatsError, compute_robustness_delta

    _ensure_database(db_path)
    try:
        report = compute_robustness_delta(
            db_path=db_path, model_alias=model_alias, mode=mode
        )
    except StatsError as exc:
        raise click.ClickException(str(exc)) from exc

    table = Table(title=f"Robustness Delta — {model_alias} (baseline − {mode})")
    table.add_column("Pillar")
    table.add_column("Baseline")
    table.add_column(mode.capitalize())
    table.add_column("Delta")
    for d in report.pillars:
        colour = "red" if d.delta > 5 else "yellow" if d.delta > 0 else "green"
        table.add_row(
            d.pillar,
            f"{d.baseline:.2f}",
            f"{d.comparison:.2f}",
            f"[{colour}]{d.delta:+.2f}[/{colour}]",
        )
    console.print(table)
    console.print(
        f"Composite delta: [bold]{report.composite_delta:+.2f}[/bold]"
    )


@main.command("compare-models")
@click.option("--model-a", required=True)
@click.option("--model-b", required=True)
@click.option("--mode", default="baseline", show_default=True)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
def compare_models_cmd(
    model_a: str, model_b: str, mode: str, db_path: Path
) -> None:
    """Pairwise Mann-Whitney U significance test per pillar."""
    from irbg.analysis.stats import StatsError, compute_pairwise_significance

    _ensure_database(db_path)
    try:
        report = compute_pairwise_significance(
            db_path=db_path, model_a=model_a, model_b=model_b, mode=mode
        )
    except StatsError as exc:
        raise click.ClickException(str(exc)) from exc

    table = Table(
        title=f"Pairwise Significance — {model_a} vs {model_b} ({mode})"
    )
    table.add_column("Pillar")
    table.add_column("n_a", justify="right")
    table.add_column("n_b", justify="right")
    table.add_column("U", justify="right")
    table.add_column("p-value", justify="right")
    table.add_column("Significant")
    for c in report.comparisons:
        sig = "[green]yes[/green]" if c.significant else "no"
        table.add_row(
            c.pillar,
            str(c.n_a),
            str(c.n_b),
            f"{c.u_statistic:.1f}",
            f"{c.p_value:.4f}",
            sig,
        )
    console.print(table)
    console.print(
        "[dim]Significance threshold: p < 0.05 (two-sided Mann-Whitney U, "
        "normal approximation)[/dim]"
    )


@main.command("verify-coverage")
@click.option("--model", "model_alias", required=True)
@click.option(
    "--scenario-dir",
    type=click.Path(path_type=Path),
    default=Path("./scenarios/v1"),
    show_default=True,
)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
def verify_coverage_cmd(
    model_alias: str, scenario_dir: Path, db_path: Path
) -> None:
    """Check that the full pillar × mode × jurisdiction matrix is covered."""
    from irbg.db.operations import get_all_runs_for_model
    from irbg.scenarios.discovery import load_template_files
    from irbg.scenarios.template_loader import load_scenario_template

    _ensure_database(db_path)

    # Build expected matrix from scenario files
    expected: set[tuple[str, str, str]] = set()
    for pillar_dir in sorted(scenario_dir.iterdir()):
        if not pillar_dir.is_dir():
            continue
        try:
            files = load_template_files(pillar_dir)
        except Exception:
            continue
        for f in files:
            t = load_scenario_template(f)
            for mode in ("baseline", "pressure"):
                expected.add((t.pillar, mode, t.jurisdiction or "unknown"))
            if t.adversarial_turns:
                expected.add(
                    (t.pillar, "adversarial", t.jurisdiction or "unknown")
                )

    # Build covered set from DB
    conn = connect(DbConfig(path=db_path))
    try:
        runs = get_all_runs_for_model(conn, model_id=model_alias)
        covered: set[tuple[str, str, str]] = set()
        for run in runs:
            rows = conn.execute(
                """
                SELECT DISTINCT s.pillar, s.jurisdiction
                FROM responses r
                JOIN scenarios s ON r.scenario_id = s.id
                WHERE r.run_id = ?
                """,
                (run["id"],),
            ).fetchall()
            for row in rows:
                covered.add(
                    (
                        str(row["pillar"]),
                        str(run["mode"]),
                        str(row["jurisdiction"] or "unknown"),
                    )
                )
    finally:
        conn.close()

    missing = sorted(expected - covered)

    table = Table(title=f"Coverage — {model_alias}")
    table.add_column("Pillar")
    table.add_column("Mode")
    table.add_column("Jurisdiction")
    table.add_column("Status")
    for cell in sorted(expected):
        status = (
            "[green]covered[/green]"
            if cell in covered
            else "[red]MISSING[/red]"
        )
        table.add_row(cell[0], cell[1], cell[2], status)
    console.print(table)

    if missing:
        console.print(
            f"[red]{len(missing)} cell(s) missing.[/red] "
            "Run the full suite before publishing results."
        )
    else:
        console.print("[green]Full matrix covered.[/green]")


@main.command("run-full-suite")
@click.option("--model", "model_alias", required=True)
@click.option(
    "--scenario-dir",
    type=click.Path(path_type=Path),
    default=Path("./scenarios/v1"),
    show_default=True,
)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=Path("./irbg.sqlite"),
    show_default=True,
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=Path("./reports"),
    show_default=True,
)
@click.option(
    "--modes",
    default="baseline,pressure",
    show_default=True,
    help="Comma-separated modes to run.",
)
def run_full_suite_cmd(
    model_alias: str,
    scenario_dir: Path,
    db_path: Path,
    output_dir: Path,
    modes: str,
) -> None:
    """Run the complete pillar × mode matrix for one model.

    Scores and reports each run. Replaces scripts/run_full_benchmark.py.
    """
    from irbg.engine.runner import RunFolderResult, run_template_folder
    from irbg.scoring.p1 import score_p1_run
    from irbg.scoring.p2 import score_p2_run
    from irbg.scoring.p3 import score_p3_run
    from irbg.scoring.p4 import score_p4_run
    from irbg.scoring.p5 import score_p5_run
    from irbg.scoring.p6 import score_p6_run

    _ensure_database(db_path)

    mode_list = [m.strip() for m in modes.split(",") if m.strip()]

    pillar_scorers = {
        "p1_demographic_consistency": score_p1_run,
        "p2_procedural_integrity": score_p2_run,
        "p3_corruption_resistance": score_p3_run,
        "p4_jurisdictional_awareness": score_p4_run,
        "p5_transparency_explainability": score_p5_run,
        "p6_minority_protection": score_p6_run,
    }

    pillar_dirs = sorted(d for d in scenario_dir.iterdir() if d.is_dir())

    run_ids: list[str] = []

    for mode in mode_list:
        for pillar_dir in pillar_dirs:
            console.print(f"[bold]Running[/bold] {pillar_dir.name} / {mode} …")
            try:
                result: RunFolderResult = run_template_folder(
                    model_alias=model_alias,
                    folder_path=pillar_dir,
                    db_path=db_path,
                    mode=mode,
                )
            except Exception as exc:
                console.print(f"  [red]FAILED:[/red] {exc}")
                continue

            run_ids.append(result.run_id)
            console.print(
                f"  run_id={result.run_id[:8]}… "
                f"ok={result.success_count} fail={result.failure_count}"
            )

            # Score the run
            try:
                scorer = pillar_scorers.get(
                    next(
                        (
                            k
                            for k in pillar_scorers
                            if pillar_dir.name.startswith(k.split("_")[0])
                        ),
                        "",
                    )
                )
                if scorer:
                    scorer(db_path=db_path, run_id=result.run_id)
            except Exception as exc:
                console.print(f"  [yellow]Score warning:[/yellow] {exc}")

            # Aggregate + report
            try:
                aggregate_run_score(db_path=db_path, run_id=result.run_id)
                report = build_run_report(db_path=db_path, run_id=result.run_id)
                write_run_report_json(
                    report=report,
                    output_path=output_dir
                    / model_alias
                    / f"{mode}_{result.run_id[:8]}_report.json",
                )
            except Exception as exc:
                console.print(f"  [yellow]Report warning:[/yellow] {exc}")

    console.print(
        f"\n[green]Done.[/green] {len(run_ids)} run(s) for {model_alias}."
    )
    console.print(
        "Run [bold]irbg verify-coverage --model "
        f"{model_alias}[/bold] to check matrix completeness."
    )
