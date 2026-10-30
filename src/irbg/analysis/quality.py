from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from irbg.db.operations import (
    DbConfig,
    connect,
    get_responses_for_run,
    get_run,
    list_benchmark_runs,
)
from irbg.scoring.quorum import MAX_INVALID_RATE

# A run with more than this share of empty/invalid responses is quarantined
# and must be excluded from published leaderboard output (and re-run).
DEFAULT_INVALID_THRESHOLD = 0.2


class QualityError(Exception):
    """Raised when run quality cannot be assessed."""


@dataclass(frozen=True)
class RunQuality:
    run_id: str
    model_alias: str
    total: int
    invalid: int
    invalid_ratio: float
    judging_invalid_ratio: float
    quarantined: bool


def _is_invalid(raw_response: str | None) -> bool:
    # "None" is the legacy artifact from the str(None) parser bug; empty /
    # whitespace covers genuine empty completions.
    text = (raw_response or "").strip()
    return not text or text == "None"


def _assess(conn, run_row, threshold: float) -> RunQuality:
    rows = get_responses_for_run(conn, run_id=str(run_row["id"]))
    total = len(rows)
    invalid = sum(1 for row in rows if _is_invalid(row["raw_response"]))
    ratio = round(invalid / total, 4) if total else 1.0
    verdict_counts = conn.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN evidence = 'insufficient_quorum' THEN 1 ELSE 0 END)
                   AS invalid
        FROM element_verdicts WHERE run_id = ?
        """,
        (str(run_row["id"]),),
    ).fetchone()
    judging_invalid_ratio = 0.0
    if verdict_counts and verdict_counts["total"]:
        judging_invalid_ratio = round(
            int(verdict_counts["invalid"]) / int(verdict_counts["total"]), 4
        )
    return RunQuality(
        run_id=str(run_row["id"]),
        model_alias=str(run_row["model_id"]),
        total=total,
        invalid=invalid,
        invalid_ratio=ratio,
        judging_invalid_ratio=judging_invalid_ratio,
        quarantined=(
            ratio > threshold or judging_invalid_ratio > MAX_INVALID_RATE
        ),
    )


def assess_run_quality(
    *,
    db_path: Path,
    run_id: str,
    threshold: float = DEFAULT_INVALID_THRESHOLD,
) -> RunQuality:
    conn = connect(DbConfig(path=db_path))
    try:
        run_row = get_run(conn, run_id=run_id)
        if run_row is None:
            raise QualityError(f"Run not found: {run_id}")
        return _assess(conn, run_row, threshold)
    finally:
        conn.close()


def assess_all_runs(
    *,
    db_path: Path,
    threshold: float = DEFAULT_INVALID_THRESHOLD,
) -> list[RunQuality]:
    conn = connect(DbConfig(path=db_path))
    try:
        return [
            _assess(conn, row, threshold) for row in list_benchmark_runs(conn)
        ]
    finally:
        conn.close()
