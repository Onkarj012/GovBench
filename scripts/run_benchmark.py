"""Idempotent GovBench runner.

Skips any (model, mode, pillar) that already has a completed run with score > 0
in the DB. Safe to re-run after interruptions.
"""

import sqlite3
import subprocess
import sys
import time

MODELS = [
    "glm-4.7-flash",
    "kimi-k2.6",
    "gpt-oss-120b",
    "deepseek-v3",
    "deepseek-v4-flash",
    "gemini-3.1-flash-lite",
    "claude-sonnet-4.6",
]

PILLAR_FOLDERS = {
    "p1_demographic_consistency": "scenarios/v1/p1_demographic",
    "p2_procedural_integrity": "scenarios/v1/p2_procedural",
    "p3_corruption_resistance": "scenarios/v1/p3_corruption",
    "p4_jurisdictional_awareness": "scenarios/v1/p4_jurisdiction",
    "p5_transparency_explainability": "scenarios/v1/p5_transparency",
    "p6_minority_protection": "scenarios/v1/p6_minority",
}

SCORING_CMD = {
    "p1_demographic_consistency": "score-p1-run",
    "p2_procedural_integrity": "score-p2-run",
    "p3_corruption_resistance": "score-p3-run",
    "p4_jurisdictional_awareness": "score-p4-run",
    "p5_transparency_explainability": "score-p5-run",
    "p6_minority_protection": "score-p6-run",
}

MODES = ["baseline", "pressure"]
DB_PATH = "irbg.sqlite"


def already_done(db: str, model: str, mode: str, pillar: str) -> bool:
    """Return True if a completed run with score > 0 exists for this combo."""
    con = sqlite3.connect(db)
    row = con.execute(
        """
        SELECT ps.score FROM benchmark_runs br
        JOIN pillar_scores ps ON ps.run_id = br.id
        WHERE br.model_id = ? AND br.mode = ? AND ps.pillar = ?
          AND br.status = 'completed' AND ps.score > 0
        LIMIT 1
        """,
        (model, mode, pillar),
    ).fetchone()
    con.close()
    return row is not None


def run(cmd: list[str]) -> tuple[int, str, str]:
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def main() -> None:
    start = time.time()
    results: dict[str, dict[str, dict[str, str]]] = {}

    for model in MODELS:
        results[model] = {}
        for mode in MODES:
            results[model][mode] = {}
            print(f"\n{'=' * 60}")
            print(f"MODEL: {model} | MODE: {mode}")
            print(f"{'=' * 60}")

            for pillar, folder in PILLAR_FOLDERS.items():
                if already_done(DB_PATH, model, mode, pillar):
                    # Fetch existing score for display
                    con = sqlite3.connect(DB_PATH)
                    row = con.execute(
                        "SELECT ps.score FROM benchmark_runs br "
                        "JOIN pillar_scores ps ON ps.run_id = br.id "
                        "WHERE br.model_id=? AND br.mode=? AND ps.pillar=? "
                        "AND br.status='completed' AND ps.score > 0 LIMIT 1",
                        (model, mode, pillar),
                    ).fetchone()
                    con.close()
                    score = f"{row[0]:.2f}" if row else "?"
                    print(f"  {pillar}: SKIP (existing score={score})")
                    results[model][mode][pillar] = f"skip:{score}"
                    continue

                print(f"  {pillar}: running...", end="", flush=True)

                # Run
                rc, stdout, stderr = run(
                    [
                        sys.executable,
                        "-m",
                        "irbg.cli",
                        "run-template-folder",
                        "--model",
                        model,
                        "--scenario-folder",
                        folder,
                        "--mode",
                        mode,
                        "--db-path",
                        DB_PATH,
                    ]
                )
                if rc != 0:
                    msg = stderr.strip().splitlines()[-1][:80]
                    print(f" FAILED ({msg})")
                    results[model][mode][pillar] = "FAILED"
                    continue

                run_id = next(
                    (
                        line.split("Run ID:")[-1].strip()
                        for line in stdout.splitlines()
                        if "Run ID:" in line
                    ),
                    None,
                )
                if not run_id:
                    print(" NO RUN ID")
                    results[model][mode][pillar] = "NO_RUN_ID"
                    continue

                # Score
                rc, stdout, stderr = run(
                    [
                        sys.executable,
                        "-m",
                        "irbg.cli",
                        SCORING_CMD[pillar],
                        "--run-id",
                        run_id,
                        "--db-path",
                        DB_PATH,
                    ]
                )
                score = next(
                    (
                        line.split("Overall Score:")[-1].strip()
                        for line in stdout.splitlines()
                        if "Overall Score:" in line
                    ),
                    "N/A",
                )

                # Aggregate + report (best-effort)
                run(
                    [
                        sys.executable,
                        "-m",
                        "irbg.cli",
                        "aggregate-run",
                        "--run-id",
                        run_id,
                        "--db-path",
                        DB_PATH,
                    ]
                )
                run(
                    [
                        sys.executable,
                        "-m",
                        "irbg.cli",
                        "report-run",
                        "--run-id",
                        run_id,
                        "--db-path",
                        DB_PATH,
                        "--output-dir",
                        "reports",
                    ]
                )

                print(f" {run_id[:8]} -> {score}")
                results[model][mode][pillar] = score

    elapsed = time.time() - start
    print(f"\n\n{'=' * 60}")
    print(f"DONE in {elapsed:.0f}s")
    print(f"{'=' * 60}\n")

    # Summary table
    pillars = list(PILLAR_FOLDERS.keys())
    header = f"{'model':<22} {'mode':<10} " + "  ".join(
        f"{p[:6]:<8}" for p in pillars
    )
    print(header)
    print("-" * len(header))
    for model in MODELS:
        for mode in MODES:
            row = f"{model:<22} {mode:<10} "
            for pillar in pillars:
                val = results[model][mode].get(pillar, "-")
                if val.startswith("skip:"):
                    val = val[5:]
                row += f"{val:<10}"
            print(row)


if __name__ == "__main__":
    main()
