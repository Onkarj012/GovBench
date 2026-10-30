from __future__ import annotations

from functools import cache
from pathlib import Path

from irbg.db.operations import DbConfig
from irbg.engine.provider import OpenRouterClient
from irbg.scenarios.template_loader import (
    ScenarioTemplateLoadError,
    load_scenario_template,
)
from irbg.scenarios.template_models import ScenarioTemplate
from irbg.scoring.judge import (
    JudgeScoringError,
    JudgeVerdict,
    score_response_rubric,
)
from irbg.scoring.rubric import parse_rubric


class ScenarioLookupError(Exception):
    """Raised when a scenario template cannot be located by id."""


def _scenario_root() -> Path:
    """Return the versioned scenario corpus root."""
    return Path(__file__).resolve().parents[3] / "scenarios" / "v1"


@cache
def _load_template(scenario_id: str) -> ScenarioTemplate | None:
    """Find and parse the scenario template with the given id, if it exists."""
    root = _scenario_root()
    if not root.exists():
        return None

    for path in root.rglob("*.json"):
        try:
            template = load_scenario_template(path)
        except ScenarioTemplateLoadError:
            continue
        if template.id == scenario_id:
            return template
    return None


def score_scenario_response(
    scenario_id: str,
    response_text: str,
    scenario_context: str,
    *,
    pillar: str,
    model_alias: str | None = None,
    db_path: Path | None = None,
    run_id: str | None = None,
    response_id: str | None = None,
    client: OpenRouterClient | None = None,
) -> JudgeVerdict | None:
    """Return a rubric-based verdict when one exists, otherwise ``None``.

    This is the single dispatch point used by all six pillar scorers:
    * if the scenario carries a rubric with elements, score via
      ``score_response_rubric``;
    * otherwise return ``None`` so the caller can fall back to its normal
      holistic or decision-based path.

    Rubric scoring failures are surfaced as ``None`` so callers can degrade
    gracefully (e.g. fall back to the holistic judge).
    """
    template = _load_template(scenario_id)
    if template is None:
        return None

    rubric_raw = getattr(template, "rubric", None)
    if not rubric_raw:
        return None

    rubric = parse_rubric(rubric_raw)
    if not rubric.elements:
        return None

    db_config = DbConfig(path=db_path) if db_path else None
    try:
        return score_response_rubric(
            template,
            response_text,
            pillar=pillar,
            db_config=db_config,
            run_id=run_id,
            response_id=response_id,
            model_alias=model_alias,
            client=client,
        )
    except JudgeScoringError:
        return None
