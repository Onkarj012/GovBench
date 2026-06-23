from __future__ import annotations

import random
from dataclasses import replace as _dc_replace
from pathlib import Path

from irbg.demographics import (
    get_variant_by_id,
    get_variant_group,
)
from irbg.engine.fact_generator import (
    FactSpace,
    parse_fact_space,
    sample_instance,
    seed_for,
)
from irbg.engine.prompt_builder import render_prompt
from irbg.scenarios.template_models import (
    RenderedPrompt,
    ScenarioTemplate,
)


class VariantGenerationError(Exception):
    """Raised when demographic variants cannot be generated."""


def generate_prompts_for_template(
    template: ScenarioTemplate,
    *,
    mode: str = "baseline",
    demographics_path: Path | None = None,
) -> list[RenderedPrompt]:
    if not template.variant_group:
        raise VariantGenerationError(
            f"Template '{template.id}' has no variant_group defined."
        )

    variants = get_variant_group(
        template.variant_group,
        path=demographics_path,
    )

    return [
        render_prompt(
            template,
            variables=variant.as_template_variables(),
            mode=mode,
            variant_id=variant.id,
        )
        for variant in variants
    ]


def generate_single_prompt_for_variant(
    template: ScenarioTemplate,
    *,
    variant_id: str,
    mode: str = "baseline",
    demographics_path: Path | None = None,
) -> RenderedPrompt:
    if not template.variant_group:
        raise VariantGenerationError(
            f"Template '{template.id}' has no variant_group defined."
        )

    variant = get_variant_by_id(
        variant_id,
        path=demographics_path,
    )

    if variant.group != template.variant_group:
        raise VariantGenerationError(
            f"Variant '{variant.id}' belongs to group '{variant.group}', "
            f"but template '{template.id}' expects group "
            f"'{template.variant_group}'."
        )

    return render_prompt(
        template,
        variables=variant.as_template_variables(),
        mode=mode,
        variant_id=variant.id,
    )


def generate_procedural_prompts(
    template: ScenarioTemplate,
    *,
    mode: str = "baseline",
    seed: int,
    n_instances: int,
    demographics_path: Path | None = None,
) -> list[RenderedPrompt]:
    """Generate prompts by sampling fact_space instances, optionally crossed
    with demographic variants.

    If *template.variant_group* is set, the result is the cross-product of
    all sampled instances and all demographic variants for that group.
    Otherwise one prompt is rendered per sampled instance.

    Args:
        template: The scenario template to render.
        mode: Prompt mode (e.g. ``"baseline"``).
        seed: Integer seed for reproducible sampling.
        n_instances: Number of fact-space instances to sample.
        demographics_path: Optional override for the demographics YAML path.

    Returns:
        A list of :class:`RenderedPrompt` objects.

    Raises:
        VariantGenerationError: If *template.fact_space* is ``None``.
    """
    if template.fact_space is None:
        raise VariantGenerationError(
            f"Template '{template.id}' has no fact_space defined."
        )

    fact_space: FactSpace = parse_fact_space(template.fact_space)
    rng = random.Random(seed_for(template.id, seed))

    instances: list[dict] = [
        sample_instance(fact_space, rng=rng, draw_index=i)
        for i in range(n_instances)
    ]

    results: list[RenderedPrompt] = []

    if template.variant_group:
        variants = get_variant_group(
            template.variant_group,
            path=demographics_path,
        )
        for i, instance_vars in enumerate(instances):
            for variant in variants:
                merged = {**instance_vars, **variant.as_template_variables()}
                rp = render_prompt(
                    template,
                    variables=merged,
                    mode=mode,
                    variant_id=f"inst{i}/{variant.id}",
                )
                results.append(_dc_replace(rp, instance_vars=instance_vars))
    else:
        for i, instance_vars in enumerate(instances):
            rp = render_prompt(
                template,
                variables=instance_vars,
                mode=mode,
                variant_id=f"inst{i}",
            )
            results.append(_dc_replace(rp, instance_vars=instance_vars))

    return results
