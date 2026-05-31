from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from irbg.paths import CONFIG_DIR


class ConfigError(Exception):
    """Raised when configuration files are missing or invalid."""


@dataclass
class ModelConfig:
    alias: str
    name: str
    provider: str
    model_id: str
    max_tokens: int
    temperature: float
    top_p: float = 0.9
    family: str = ""
    # USD per 1M tokens; used to compute cost when the provider does not
    # report one. reasoning: None (model default) | "off" | effort level.
    price_input: float = 0.0
    price_output: float = 0.0
    reasoning: str | None = None


def load_model_config(
    path: Path | None = None,
) -> dict[str, ModelConfig]:
    config_path = path or (CONFIG_DIR / "models.yaml")

    if not config_path.exists():
        raise ConfigError(f"Model config file not found at {config_path}")

    raw_data = yaml.safe_load(config_path.read_text()) or {}
    raw_models = raw_data.get("models")

    if not isinstance(raw_models, dict):
        raise ConfigError(
            "Invalid models.yaml: expected a top-level 'models' mapping."
        )

    models: dict[str, ModelConfig] = {}

    for alias, values in raw_models.items():
        if not isinstance(values, dict):
            raise ConfigError(
                "Invalid models.yaml: expected a mapping for model alias "
                f"'{alias}'"
            )

        try:
            models[alias] = ModelConfig(
                alias=alias,
                name=str(values["name"]),
                provider=str(values["provider"]),
                model_id=str(values["model_id"]),
                max_tokens=int(values["max_tokens"]),
                temperature=float(values["temperature"]),
                top_p=float(values.get("top_p", 0.9)),
                family=str(
                    values.get("family")
                    or str(values["model_id"]).split("/")[0]
                ),
                price_input=float(values.get("price_input", 0.0)),
                price_output=float(values.get("price_output", 0.0)),
                reasoning=(
                    str(values["reasoning"])
                    if values.get("reasoning") is not None
                    else None
                ),
            )
        except KeyError as exc:
            raise ConfigError(
                f"Missing required Key for model '{alias}': {exc}"
            ) from exc

    return models


def load_models_config(
    path: Path | None = None,
) -> dict[str, ModelConfig]:
    """
    Backwards-compatible alias for loading all model configurations.

    Kept for compatibility with earlier APIs and existing tests that
    expect a pluralized function name.
    """
    return load_model_config(path=path)


def get_model_config(
    alias: str,
    path: Path | None = None,
) -> ModelConfig:
    models = load_model_config(path=path)

    try:
        return models[alias]
    except KeyError as exc:
        available = ", ".join(sorted(models.keys()))
        raise ConfigError(
            f"Unknown model alias '{alias}'. Available models: {available}"
        ) from exc


def _load_raw(path: Path | None) -> dict:
    config_path = path or (CONFIG_DIR / "models.yaml")
    if not config_path.exists():
        raise ConfigError(f"Model config file not found at {config_path}")
    return yaml.safe_load(config_path.read_text()) or {}


def load_judge_models(path: Path | None = None) -> list[str]:
    """Judge model aliases for the scoring ensemble.

    Falls back to the single ``judge_model`` key, then to ``gpt-4o``.
    """
    raw = _load_raw(path)
    judges = raw.get("judge_models")
    if isinstance(judges, list) and judges:
        return [str(j) for j in judges]
    single = raw.get("judge_model")
    return [str(single)] if single else ["gpt-4o"]


def load_pillar_weights(path: Path | None = None) -> dict[str, float]:
    """Per-pillar composite weights; empty dict if unspecified."""
    raw = _load_raw(path)
    weights = raw.get("pillar_weights")
    if isinstance(weights, dict):
        return {str(k): float(v) for k, v in weights.items()}
    return {}
