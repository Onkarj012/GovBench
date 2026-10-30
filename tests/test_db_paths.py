from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from irbg.cli import main
from irbg.db.operations import DbConfig, connect
from irbg.paths import DEFAULT_DB_PATH, PROJECT_ROOT


def test_default_db_path_points_at_project_root() -> None:
    assert DEFAULT_DB_PATH == PROJECT_ROOT / "irbg.sqlite"


def test_mark_stale_runs_marks_running_as_failed(tmp_path: Path) -> None:
    db_path = tmp_path / "irbg.sqlite"
    conn = connect(DbConfig(path=db_path))
    try:
        conn.execute(
            """
            CREATE TABLE benchmark_runs (
                id TEXT PRIMARY KEY,
                model_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                config_snapshot TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO benchmark_runs "
            "(id, model_id, mode, status, started_at)"
            " VALUES ('run-1', 'model-a', 'baseline', 'running', '2026-01-01');"
        )
        conn.execute(
            "INSERT INTO benchmark_runs "
            "(id, model_id, mode, status, started_at)"
            " VALUES ('run-2', 'model-a', 'baseline', 'completed', "
            "'2026-01-01');"
        )
        conn.commit()
    finally:
        conn.close()

    runner = CliRunner()
    result = runner.invoke(main, ["mark-stale-runs", "--db-path", str(db_path)])
    assert result.exit_code == 0

    conn = connect(DbConfig(path=db_path))
    try:
        statuses = dict(conn.execute("SELECT id, status FROM benchmark_runs;"))
    finally:
        conn.close()

    assert statuses == {"run-1": "failed", "run-2": "completed"}
