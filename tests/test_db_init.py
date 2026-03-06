from __future__ import annotations

import sqlite3

from irbg.db.schema import create_tables


def test_create_tables_idempotent() -> None:
    conn = sqlite3.connect(":memory:")
    create_tables(conn)
    # Running twice should not fail.
    create_tables(conn)

    # Validate a couple of expected tables exist.
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='models';"
    )
    assert cur.fetchone() is not None

    cur = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='benchmark_runs';"
    )
    assert cur.fetchone() is not None

    conn.close()
