from __future__ import annotations

from pathlib import Path

import pytest

from irbg.engine.variant_generator import (
    VariantGenerationError,
    generate_procedural_prompts,
    generate_prompts_for_template,
    generate_single_prompt_for_variant,
)
from irbg.scenarios.template_models import ScenarioTemplate


def test_generate_single_prompt_for_variant(tmp_path: Path) -> None:
    demographics_file = tmp_path / "demographics.yaml"
    demographics_file.write_text(
        """
variant_groups:
  test_group:
    - id: test_1
      name: Test User
      age: 30
      gender: male
      nationality: Indian
      religion: Hindu
      background: lives in Pune
      socioeconomic_signal: middle_class
"""
    )

    template = ScenarioTemplate(
        id="TEST-001",
        pillar="p1",
        category="demo",
        jurisdiction="India",
        difficulty="easy",
        system_prompt_template="You are an officer.",
        user_prompt_template="Review {name}, age {age}, who {background}.",
        static_variables={},
        variant_group="test_group",
        modes={},
    )

    rendered = generate_single_prompt_for_variant(
        template,
        variant_id="test_1",
        mode="baseline",
        demographics_path=demographics_file,
    )

    assert rendered.variant_id == "test_1"
    assert "Test User" in rendered.user_prompt


def test_generate_prompts_for_template(tmp_path: Path) -> None:
    demographics_file = tmp_path / "demographics.yaml"
    demographics_file.write_text(
        """
variant_groups:
  test_group:
    - id: test_1
      name: User One
      age: 30
      gender: male
      nationality: Indian
      religion: Hindu
      background: lives in Pune
      socioeconomic_signal: middle_class
    - id: test_2
      name: User Two
      age: 30
      gender: female
      nationality: Indian
      religion: Muslim
      background: lives in Pune
      socioeconomic_signal: middle_class
"""
    )

    template = ScenarioTemplate(
        id="TEST-002",
        pillar="p1",
        category="demo",
        jurisdiction="India",
        difficulty="easy",
        system_prompt_template="You are an officer.",
        user_prompt_template="Review {name}.",
        static_variables={},
        variant_group="test_group",
        modes={},
    )

    rendered_prompts = generate_prompts_for_template(
        template,
        mode="baseline",
        demographics_path=demographics_file,
    )

    assert len(rendered_prompts) == 2
    assert rendered_prompts[0].variant_id == "test_1"
    assert rendered_prompts[1].variant_id == "test_2"


# ---------------------------------------------------------------------------
# generate_procedural_prompts
# ---------------------------------------------------------------------------

_FACT_SPACE_RAW = {
    "fields": [
        {"name": "color", "type": "choice", "values": ["red", "blue", "green"]},
    ]
}


def _make_procedural_template(
    *,
    with_fact_space: bool = True,
    variant_group: str | None = None,
) -> ScenarioTemplate:
    return ScenarioTemplate(
        id="PROC-001",
        pillar="p1",
        category="test",
        jurisdiction=None,
        difficulty=None,
        system_prompt_template="System.",
        user_prompt_template="The color is {color}.",
        static_variables={},
        variant_group=variant_group,
        modes={},
        fact_space=_FACT_SPACE_RAW if with_fact_space else None,
    )


def test_procedural_count_no_demographics() -> None:
    template = _make_procedural_template()
    prompts = generate_procedural_prompts(template, seed=0, n_instances=5)
    assert len(prompts) == 5


def test_procedural_no_fact_space_raises() -> None:
    template = _make_procedural_template(with_fact_space=False)
    with pytest.raises(VariantGenerationError):
        generate_procedural_prompts(template, seed=0, n_instances=3)


def test_procedural_variant_ids_unique() -> None:
    template = _make_procedural_template()
    prompts = generate_procedural_prompts(template, seed=7, n_instances=6)
    variant_ids = [p.variant_id for p in prompts]
    assert len(variant_ids) == len(set(variant_ids))
