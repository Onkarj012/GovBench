from __future__ import annotations

from pathlib import Path

from irbg.db.operations import (
    DbConfig,
    connect,
    get_element_pass_matrix,
    insert_element_verdict,
    now_utc_iso,
)
from irbg.db.schema import create_tables


def test_insert_and_retrieve_verdict(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite"
    conn = connect(DbConfig(path=db_path))
    create_tables(conn)

    verdict_id = insert_element_verdict(
        conn,
        run_id="run-001",
        scenario_id="scenario-001",
        element_id="reject_single_source",
        present=True,
        evidence="lexical: 'competitive tender'",
        created_at=now_utc_iso(),
    )

    row = conn.execute(
        "SELECT * FROM element_verdicts WHERE id = ?",
        (verdict_id,),
    ).fetchone()

    assert row is not None
    assert row["run_id"] == "run-001"
    assert row["scenario_id"] == "scenario-001"
    assert row["element_id"] == "reject_single_source"
    assert row["present"] == 1
    assert row["evidence"] == "lexical: 'competitive tender'"

    conn.close()


def test_insert_absent_verdict_stores_zero(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite"
    conn = connect(DbConfig(path=db_path))
    create_tables(conn)

    verdict_id = insert_element_verdict(
        conn,
        run_id="run-002",
        scenario_id="scenario-002",
        element_id="flag_fake_precedent",
        present=False,
        evidence="not detected",
        created_at=now_utc_iso(),
    )

    row = conn.execute(
        "SELECT * FROM element_verdicts WHERE id = ?",
        (verdict_id,),
    ).fetchone()

    assert row is not None
    assert row["present"] == 0

    conn.close()


def test_pass_matrix_empty(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite"
    conn = connect(DbConfig(path=db_path))
    create_tables(conn)

    result = get_element_pass_matrix(conn)

    assert result == []

    conn.close()


def test_pass_matrix_aggregates_correctly(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite"
    conn = connect(DbConfig(path=db_path))
    create_tables(conn)

    ts = now_utc_iso()
    insert_element_verdict(
        conn,
        run_id="run-a",
        scenario_id="s1",
        element_id="elem1",
        present=True,
        evidence="ok",
        created_at=ts,
    )
    insert_element_verdict(
        conn,
        run_id="run-b",
        scenario_id="s1",
        element_id="elem1",
        present=False,
        evidence="missing",
        created_at=ts,
    )

    matrix = get_element_pass_matrix(conn)

    assert len(matrix) == 1
    row = matrix[0]
    assert row["element_id"] == "elem1"
    assert row["scenario_id"] == "s1"
    assert row["present_count"] == 1
    assert row["total_count"] == 2

    conn.close()
