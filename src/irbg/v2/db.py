from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from irbg.db.operations import DbConfig, connect
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
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'pressure',
    attempts_json TEXT NOT NULL DEFAULT '[]'
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
CREATE TABLE IF NOT EXISTS budget_charges (
    call_id TEXT PRIMARY KEY,
    episode_id TEXT NOT NULL,
    run_name TEXT NOT NULL,
    cost_usd REAL NOT NULL
);
"""


def now_iso() -> str:
    """Current UTC time in ISO 8601."""
    return datetime.now(UTC).isoformat()


def connect_v2(path: Path | None = None) -> sqlite3.Connection:
    """Open the v2 database, creating it and its tables if needed."""
    p = path or DEFAULT_DB
    conn = connect(DbConfig(path=p))
    try:
        conn.execute("PRAGMA busy_timeout = 60000")
        conn.executescript(_SCHEMA)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(episodes)")}
        if "kind" not in cols:
            # Databases from before control episodes existed.
            conn.execute(
                "ALTER TABLE episodes ADD COLUMN kind TEXT NOT NULL "
                "DEFAULT 'pressure'"
            )
            conn.commit()
        if "attempts_json" not in cols:
            conn.execute(
                "ALTER TABLE episodes ADD COLUMN attempts_json TEXT NOT NULL "
                "DEFAULT '[]'"
            )
            conn.commit()
    except BaseException:
        conn.close()
        raise
    return conn


def episode_key(
    run_name: str,
    model: str,
    scenario: str,
    stance: str,
    seed: int,
    kind: str = "pressure",
) -> str:
    """Stable episode id so a rerun skips finished work."""
    key = f"{run_name}|{model}|{scenario}|{stance}|{seed}"
    return key if kind == "pressure" else f"{key}|{kind}"


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
    """Sum per-call charges and legacy episode costs without double counting."""
    row = conn.execute(
        "SELECT COALESCE((SELECT SUM(cost_usd) FROM episodes e "
        "WHERE e.run_name = ? AND NOT EXISTS (SELECT 1 FROM budget_charges b "
        "WHERE b.episode_id = e.id AND b.call_id = 'baseline:' || e.id)), 0) + "
        "COALESCE((SELECT SUM(cost_usd) FROM budget_charges "
        "WHERE run_name = ?), 0) AS c",
        (run_name, run_name),
    ).fetchone()
    return float(row["c"])


def record_budget_charge(
    conn: sqlite3.Connection,
    call_id: str,
    episode_id: str,
    run_name: str,
    cost_usd: float,
) -> None:
    """Persist a paid call before another worker checks the cap."""
    _ensure_baseline_charge(conn, episode_id, run_name)
    conn.execute(
        "INSERT OR IGNORE INTO budget_charges VALUES (?, ?, ?, ?)",
        (call_id, episode_id, run_name, cost_usd),
    )
    conn.commit()


def save_episode(conn: sqlite3.Connection, row: dict) -> None:
    """Preserve completed episodes and invalidate stale judge results."""
    previous = conn.execute(
        "SELECT status, turns_json FROM episodes WHERE id = ?",
        (row["id"],),
    ).fetchone()
    if previous and previous["status"] == "complete":
        return
    if previous and previous["turns_json"] != row["turns_json"]:
        conn.execute("DELETE FROM verdicts WHERE episode_id = ?", (row["id"],))
        conn.execute(
            "DELETE FROM classifications WHERE episode_id = ?", (row["id"],)
        )
    charge_total = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM budget_charges "
        "WHERE episode_id = ?",
        (row["id"],),
    ).fetchone()[0]
    if charge_total:
        row = {**row, "cost_usd": float(charge_total)}
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    updates = ", ".join(f"{col} = excluded.{col}" for col in row if col != "id")
    conn.execute(
        f"INSERT INTO episodes ({cols}) VALUES ({marks}) "
        f"ON CONFLICT(id) DO UPDATE SET {updates} "
        "WHERE episodes.status != 'complete'",
        tuple(row.values()),
    )
    conn.commit()


def _ensure_baseline_charge(
    conn: sqlite3.Connection, episode_id: str, run_name: str
) -> None:
    """Record an existing episode cost before its first ledger-backed save."""
    baseline_id = f"baseline:{episode_id}"
    if (
        conn.execute(
            "SELECT 1 FROM budget_charges WHERE call_id = ?", (baseline_id,)
        ).fetchone()
        is not None
    ):
        return
    legacy = conn.execute(
        "SELECT cost_usd FROM episodes WHERE id = ?", (episode_id,)
    ).fetchone()
    cost = legacy["cost_usd"] if legacy is not None else 0.0
    conn.execute(
        "INSERT OR IGNORE INTO budget_charges VALUES (?, ?, ?, ?)",
        (baseline_id, episode_id, run_name, cost),
    )
