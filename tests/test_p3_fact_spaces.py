from __future__ import annotations

import re
from pathlib import Path

import pytest

from irbg.engine.fact_generator import (
    parse_fact_space,
    sample_instance,
    seed_for,
)
from irbg.engine.prompt_builder import render_prompt
from irbg.scenarios.template_loader import load_scenario_template

_P3_DIR = Path(__file__).parent.parent / "scenarios" / "v1" / "p3_corruption"
_LEFTOVER_BRACE_RE = re.compile(r"\{[^{}]+\}")


def _all_p3_paths() -> list[Path]:
    return sorted(_P3_DIR.glob("*.json"))


@pytest.mark.parametrize("path", _all_p3_paths(), ids=lambda p: p.name)
def test_p3_fact_space_renders_no_leftover_placeholders(path: Path) -> None:
    template = load_scenario_template(path)
    assert template.fact_space is not None, f"{path.name} has no fact_space"

    fact_space = parse_fact_space(template.fact_space)
    seed = seed_for(template.id, 42)
    rng_a = __import__("random").Random(seed)

    rendered_prompts: list[str] = []
    for i in range(5):
        instance_vars = sample_instance(fact_space, rng=rng_a, draw_index=i)
        rendered = render_prompt(
            template,
            variables=instance_vars,
            mode="baseline",
            variant_id=f"inst{i}",
        )
        rendered_prompts.append(
            rendered.system_prompt + "\n" + rendered.user_prompt
        )

    for text in rendered_prompts:
        matches = _LEFTOVER_BRACE_RE.findall(text)
        assert not matches, f"Leftover placeholders in {path.name}: {matches}"


@pytest.mark.parametrize("path", _all_p3_paths(), ids=lambda p: p.name)
def test_p3_instances_differ_across_seeds(path: Path) -> None:
    template = load_scenario_template(path)
    assert template.fact_space is not None
    fact_space = parse_fact_space(template.fact_space)

    seed_a = seed_for(template.id, 0)
    seed_b = seed_for(template.id, 1)
    rng_a = __import__("random").Random(seed_a)
    rng_b = __import__("random").Random(seed_b)

    instances_a = [
        sample_instance(fact_space, rng=rng_a, draw_index=i) for i in range(5)
    ]
    instances_b = [
        sample_instance(fact_space, rng=rng_b, draw_index=i) for i in range(5)
    ]

    assert instances_a != instances_b, (
        f"Instances for {path.name} are identical across seeds"
    )


def test_p3_directory_contains_expected_scenarios() -> None:
    paths = _all_p3_paths()
    assert len(paths) == 17, f"Expected 17 p3 scenarios, found {len(paths)}"
