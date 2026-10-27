from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from irbg.paths import PROJECT_ROOT

DEFAULT_DB = PROJECT_ROOT / "outputs" / "v2" / "govbench-v2.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_name TEXT PRIMARY KEY,
    manifest_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS episodes (
    id TEXT PRIMARY KEY,
    run_name TEXT NOT NULL,
    model_alias TEXT NOT NULL,
    backend TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    role TEXT NOT NULL,
    pressure TEXT NOT NULL,
    split TEXT NOT NULL,
    review_status TEXT NOT NULL,
    stance TEXT NOT NULL,
    seed INTEGER NOT NULL,
    instance_json TEXT NOT NULL,
    system_prompt TEXT NOT NULL,
    turns_json TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    turn0_decision TEXT,
    turn0_correct INTEGER,
    break_turn INTEGER,
    cost_usd REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS episodes_run ON episodes (run_name, model_alias);
CREATE TABLE IF NOT EXISTS verdicts (
    episode_id TEXT NOT NULL,
    judge TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    verdict_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (episode_id, judge, prompt_hash)
);
CREATE TABLE IF NOT EXISTS classifications (
    episode_id TEXT PRIMARY KEY,
    class TEXT NOT NULL,
    escalate INTEGER,
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def now_iso() -> str:
    """Current UTC time in ISO 8601."""
    return datetime.now(UTC).isoformat()


def connect_v2(path: Path | None = None) -> sqlite3.Connection:
    """Open the v2 database, creating it and its tables if needed."""
    p = path or DEFAULT_DB
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def episode_key(
    run_name: str, model: str, scenario: str, stance: str, seed: int
) -> str:
    """Stable episode id so a rerun skips finished work."""
    return f"{run_name}|{model}|{scenario}|{stance}|{seed}"


def save_manifest(
    conn: sqlite3.Connection, run_name: str, manifest: dict
) -> None:
    """Insert or replace the manifest for a run."""
    conn.execute(
        "INSERT OR REPLACE INTO runs VALUES (?, ?, ?)",
        (run_name, json.dumps(manifest, sort_keys=True), now_iso()),
    )
    conn.commit()


def completed_keys(conn: sqlite3.Connection, run_name: str) -> set[str]:
    """Episode ids already completed for a run."""
    rows = conn.execute(
        "SELECT id FROM episodes WHERE run_name = ? AND status = 'complete'",
        (run_name,),
    )
    return {r["id"] for r in rows}


def run_cost(conn: sqlite3.Connection, run_name: str) -> float:
    """Summed OpenRouter spend recorded for a run."""
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) AS c FROM episodes "
        "WHERE run_name = ?",
        (run_name,),
    ).fetchone()
    return float(row["c"])


def save_episode(conn: sqlite3.Connection, row: dict) -> None:
    """Insert or replace one episode row."""
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    conn.execute(
        f"INSERT OR REPLACE INTO episodes ({cols}) VALUES ({marks})",
        tuple(row.values()),
    )
    conn.commit()
