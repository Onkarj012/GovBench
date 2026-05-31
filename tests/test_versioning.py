from __future__ import annotations

import json
from pathlib import Path

from irbg.scenarios.template_loader import load_scenario_template


def _write_template(tmp_path: Path, extra: dict) -> Path:
    data = {
        "id": "TEST-001",
        "pillar": "p1_demographic_consistency",
        "category": "bail_recommendation",
        "system_prompt_template": "You are a legal advisor.",
        "user_prompt_template": "Review {name}.",
        **extra,
    }
    p = tmp_path / "t.json"
    p.write_text(json.dumps(data))
    return p


def test_version_defaults_to_v1(tmp_path: Path) -> None:
    t = load_scenario_template(_write_template(tmp_path, {}))
    assert t.version == "v1"


def test_version_explicit(tmp_path: Path) -> None:
    t = load_scenario_template(_write_template(tmp_path, {"version": "v2"}))
    assert t.version == "v2"


def test_canary_loaded(tmp_path: Path) -> None:
    t = load_scenario_template(
        _write_template(tmp_path, {"canary": "GOVBENCH-CANARY-TEST-001"})
    )
    assert t.canary == "GOVBENCH-CANARY-TEST-001"


def test_canary_defaults_empty(tmp_path: Path) -> None:
    t = load_scenario_template(_write_template(tmp_path, {}))
    assert t.canary == ""
