from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
SCENARIOS_DIR = PROJECT_ROOT / "scenarios"
DEFAULT_DB_PATH = PROJECT_ROOT / "irbg.sqlite"
