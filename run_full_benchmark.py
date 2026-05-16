"""Full IRBG benchmark runner - all pillars, all models, baseline + pressure."""

import subprocess
import sys
import time
from pathlib import Path

MODELS = [
    "gpt-oss-120b",
    "glm-4.7-flash",
    "deepseek-v4-flash",
    "gemini-3.1-flash-lite",
    "claude-sonnet-4.6",
]

PILLAR_FOLDERS = {
    "p1": "scenarios/p1_consistency",
    "p2": "scenarios/p2_procedural",
    "p3": "scenarios/p3_corruption",
    "p4": "scenarios/p4_jurisdiction",
    "p5": "scenarios/p5_transparency",
    "p6": "scenarios/p6_minority",
}

MODES = ["baseline", "pressure"]

SCORING_COMMANDS = {
    "p1": "score-p1-run",
    "p2": "score-p2-run",
    "p3": "score-p3-run",
    "p4": "score-p4-run",
    "p5": "score-p5-run",
    "p6": "score-p6-run",
}

DB_PATH = Path("irbg.sqlite")
REPORTS_DIR = Path("reports")


def run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def run_benchmark():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    start_time = time.time()

    summary: dict[str, dict[str, dict[str, dict[str, str | float]]]] = {}

    for model in MODELS:
        summary[model] = {}
        for mode in MODES:
            summary[model][mode] = {}
            run_ids: dict[str, str] = {}

            print(f"\n{'='*60}")
            print(f"MODEL: {model} | MODE: {mode}")
            print(f"{'='*60}")

            # Phase 1: Run all pillar folders
            for pillar, folder in PILLAR_FOLDERS.items():
                print(f"\n--- Running {pillar} ({folder}) ---")
                rc, stdout, stderr = run_cmd([
                    sys.executable, "-m", "irbg.cli",
                    "run-template-folder",
                    "--model", model,
                    "--scenario-folder", folder,
                    "--mode", mode,
                    "--db-path", str(DB_PATH),
                ])

                if rc != 0:
                    print(f"  FAILED: {stderr.strip()}")
                    run_ids[pillar] = "FAILED"
                    continue

                # Extract run_id from stdout (format: Run ID: <uuid>)
                for line in stdout.splitlines():
                    if "Run ID:" in line:
                        run_id = line.split("Run ID:")[-1].strip()
                        run_ids[pillar] = run_id
                        print(f"  Run ID: {run_id}")
                        break

            # Phase 2: Score each run
            for pillar, run_id in run_ids.items():
                if run_id == "FAILED":
                    continue
                print(f"\n--- Scoring {pillar} (run {run_id[:8]}...) ---")
                score_cmd = SCORING_COMMANDS[pillar]
                rc, stdout, stderr = run_cmd([
                    sys.executable, "-m", "irbg.cli",
                    score_cmd,
                    "--run-id", run_id,
                    "--db-path", str(DB_PATH),
                ])

                if rc != 0:
                    print(f"  SCORE FAILED: {stderr.strip()}")
                    summary[model][mode][pillar] = "SCORE_FAILED"
                    continue

                for line in stdout.splitlines():
                    if "Overall Score:" in line:
                        score = line.split("Overall Score:")[-1].strip()
                        summary[model][mode][pillar] = score
                        print(f"  Score: {score}")
                        break

            # Phase 3: Aggregate and report for each pillar run
            for _pillar, run_id in run_ids.items():
                if run_id == "FAILED":
                    continue
                try:
                    run_cmd([
                        sys.executable, "-m", "irbg.cli",
                        "aggregate-run",
                        "--run-id", run_id,
                        "--db-path", str(DB_PATH),
                    ])

                    run_cmd([
                        sys.executable, "-m", "irbg.cli",
                        "report-run",
                        "--run-id", run_id,
                        "--db-path", str(DB_PATH),
                        "--output-dir", str(REPORTS_DIR),
                    ])
                except Exception:
                    pass

    elapsed = time.time() - start_time
    print(f"\n\n{'='*60}")
    print(f"BENCHMARK COMPLETE in {elapsed:.0f}s")
    print(f"{'='*60}")

    print("\n## RESULTS SUMMARY\n")
    for model in MODELS:
        print(f"### {model}")
        for mode in MODES:
            print(f"  {mode}:")
            for pillar in PILLAR_FOLDERS:
                score = summary[model][mode].get(pillar, "N/A")
                print(f"    {pillar}: {score}")


if __name__ == "__main__":
    run_benchmark()
