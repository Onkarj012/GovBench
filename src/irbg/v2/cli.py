from __future__ import annotations

import json
from pathlib import Path

import click

from irbg.paths import PROJECT_ROOT
from irbg.scenarios.v2 import ScenarioV2, ScenarioV2Error, load_v2_folder
from irbg.v2.classify import classify_run
from irbg.v2.config import STANCES, V2ConfigError, load_v2_config
from irbg.v2.db import DEFAULT_DB, connect_v2, save_manifest
from irbg.v2.matrix import build_export
from irbg.v2.runner import build_manifest, run_model, validate_run_identity

PUBLIC_DIR = PROJECT_ROOT / "scenarios" / "v2"
PRIVATE_DIR = PROJECT_ROOT / "scenarios" / "holdout" / "v2"


def _scenarios(splits: tuple[str, ...]) -> list[ScenarioV2]:
    """Load public and private v2 scenarios for the requested splits."""
    found: list[ScenarioV2] = []
    for folder in (PUBLIC_DIR, PRIVATE_DIR):
        if folder.exists():
            found.extend(load_v2_folder(folder))
    ids = [s.id for s in found]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise click.ClickException(f"duplicate scenario ids: {dupes}")
    return [s for s in found if s.split in splits]


def _log(msg: str) -> None:
    """Print a progress line immediately."""
    click.echo(msg)


@click.group("v2")
def v2() -> None:
    """GovBench v2: role x pressure episodes."""


@v2.command("run")
@click.option("--run-name", required=True)
@click.option("--models", "model_list", default="", help="Comma list.")
@click.option("--seeds", type=int, default=None, help="Override seeds.")
@click.option("--stance", type=click.Choice(["both", *STANCES]), default="both")
@click.option("--splits", default="public,private")
@click.option("--only", default="", help="Comma list of scenario ids.")
@click.option(
    "--max-usd",
    type=click.FloatRange(min=0),
    default=10.0,
    help="OpenRouter threshold; a call may exceed it. CLI costs excluded.",
)
@click.option("--db", "db_path", type=click.Path(path_type=Path))
def run_cmd(
    run_name: str,
    model_list: str,
    seeds: int | None,
    stance: str,
    splits: str,
    only: str,
    max_usd: float,
    db_path: Path | None,
) -> None:
    """Run pending episodes for each model (resumable, cost-capped)."""
    try:
        cfg = load_v2_config()
        scenarios = _scenarios(tuple(splits.split(",")))
    except (V2ConfigError, ScenarioV2Error) as exc:
        raise click.ClickException(str(exc)) from exc
    if only:
        wanted = set(only.split(","))
        scenarios = [s for s in scenarios if s.id in wanted]
    aliases = model_list.split(",") if model_list else list(cfg.models)
    unknown = [a for a in aliases if a not in cfg.models]
    if unknown:
        raise click.ClickException(f"unknown models: {unknown}")
    stances = STANCES if stance == "both" else (stance,)
    _log(
        "Budget limit uses recorded or configured OpenRouter pricing; a call "
        "may exceed the cap, and --max-usd cannot measure CLI backend costs."
    )
    conn = connect_v2(db_path)
    try:
        existing = conn.execute(
            "SELECT 1 FROM runs WHERE run_name = ?", (run_name,)
        ).fetchone()
        if existing:
            try:
                validate_run_identity(
                    conn,
                    run_name,
                    cfg,
                    {s.id: s for s in scenarios},
                    exact_scenarios=True,
                    seeds=seeds,
                )
            except ValueError as exc:
                raise click.ClickException(str(exc)) from exc
        else:
            save_manifest(
                conn,
                run_name,
                build_manifest(cfg, scenarios, run_name, seeds=seeds),
            )
        for alias in aliases:
            counts = run_model(
                conn=conn,
                cfg=cfg,
                model=cfg.models[alias],
                scenarios=scenarios,
                run_name=run_name,
                seeds=seeds,
                stances=stances,
                max_usd=max_usd,
                log=_log,
            )
            _log(f"[{alias}] done {counts}")
    finally:
        conn.close()


@v2.command("classify")
@click.option("--run-name", required=True)
@click.option("--workers", type=int, default=4)
@click.option(
    "--judges",
    "ask",
    help="Comma-separated judge aliases to ask now (default: all).",
)
@click.option("--db", "db_path", type=click.Path(path_type=Path))
def classify_cmd(
    run_name: str, workers: int, ask: str | None, db_path: Path | None
) -> None:
    """Collect blind panel verdicts and classify every episode."""
    try:
        cfg = load_v2_config()
        scenarios = {s.id: s for s in _scenarios(("public", "private"))}
    except (V2ConfigError, ScenarioV2Error) as exc:
        raise click.ClickException(str(exc)) from exc
    known = {j.alias for j in cfg.judges}
    ask_set = set(ask.split(",")) if ask else known
    if not ask_set <= known:
        raise click.ClickException(f"unknown judge: {ask_set - known}")
    conn = connect_v2(db_path)
    try:
        try:
            validate_run_identity(conn, run_name, cfg, scenarios)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        counts = classify_run(
            conn=conn,
            run_name=run_name,
            scenarios=scenarios,
            judges=cfg.judges,
            ask=ask_set,
            workers=workers,
            log=_log,
        )
    finally:
        conn.close()
    _log(json.dumps(counts, indent=2, sort_keys=True))


@v2.command("export")
@click.option("--run-name", required=True)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=PROJECT_ROOT / "frontend" / "public" / "data" / "v2.json",
)
@click.option("--include-draft", is_flag=True, help="Show unreviewed cases.")
@click.option("--db", "db_path", type=click.Path(path_type=Path))
def export_cmd(
    run_name: str, out: Path, include_draft: bool, db_path: Path | None
) -> None:
    """Write the site JSON for a classified run."""
    try:
        cfg = load_v2_config()
        scenarios = {s.id: s for s in _scenarios(("public", "private"))}
    except (V2ConfigError, ScenarioV2Error) as exc:
        raise click.ClickException(str(exc)) from exc
    conn = connect_v2(db_path)
    try:
        try:
            validate_run_identity(conn, run_name, cfg, scenarios)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        data = build_export(
            conn=conn,
            cfg=cfg,
            scenarios=scenarios,
            run_name=run_name,
            include_draft=include_draft,
        )
    finally:
        conn.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1, sort_keys=True))
    _log(f"wrote {out} ({len(data['models'])} models)")


@v2.command("status")
@click.option("--run-name", required=True)
@click.option("--db", "db_path", type=click.Path(path_type=Path))
def status_cmd(run_name: str, db_path: Path | None) -> None:
    """Episode and classification counts per model."""
    conn = connect_v2(db_path or DEFAULT_DB)
    try:
        rows = conn.execute(
            "SELECT e.model_alias, e.status, COUNT(*) n, "
            "SUM(e.cost_usd) cost, COUNT(c.class) classified "
            "FROM episodes e LEFT JOIN classifications c "
            "ON c.episode_id = e.id WHERE e.run_name = ? "
            "GROUP BY 1, 2 ORDER BY 1, 2",
            (run_name,),
        ).fetchall()
    finally:
        conn.close()
    for r in rows:
        _log(
            f"{r['model_alias']:22} {r['status']:9} n={r['n']:4} "
            f"classified={r['classified']:4} cost=${r['cost'] or 0:.3f}"
        )
