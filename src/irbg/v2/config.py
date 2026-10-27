from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from irbg.paths import CONFIG_DIR

BACKENDS = ("openrouter", "codex", "claude_code")
STANCES = ("decision_maker", "advisor")


class V2ConfigError(Exception):
    """Raised when config/v2.yaml is missing or invalid."""


@dataclass(frozen=True)
class V2Model:
    alias: str
    name: str
    family: str
    backend: str
    model_id: str
    seeds: int
    workers: int
    max_tokens: int = 4096
    temperature: float = 0.0
    price_input: float = 0.0
    price_output: float = 0.0


@dataclass(frozen=True)
class V2Judge:
    alias: str
    backend: str
    model_id: str


@dataclass(frozen=True)
class V2Config:
    models: dict[str, V2Model]
    judges: tuple[V2Judge, ...]
    roles: dict[str, dict[str, str]]

    def role_prompt(self, role: str, stance: str) -> str:
        """System prompt for a role in a stance."""
        try:
            return self.roles[role][stance].strip()
        except KeyError as exc:
            raise V2ConfigError(f"no prompt for {role}/{stance}") from exc


def load_v2_config(path: Path | None = None) -> V2Config:
    """Read and validate config/v2.yaml."""
    p = path or (CONFIG_DIR / "v2.yaml")
    if not p.exists():
        raise V2ConfigError(f"missing {p}")
    raw = yaml.safe_load(p.read_text()) or {}
    try:
        models = {
            alias: V2Model(alias=alias, **values)
            for alias, values in raw["models"].items()
        }
        judges = tuple(
            V2Judge(alias=alias, **values)
            for alias, values in raw["judges"].items()
        )
        roles = {
            role: {k: str(v) for k, v in stances.items()}
            for role, stances in raw["roles"].items()
        }
    except (KeyError, TypeError) as exc:
        raise V2ConfigError(f"invalid {p}: {exc!r}") from exc
    for m in [*models.values(), *judges]:
        if m.backend not in BACKENDS:
            raise V2ConfigError(f"{m.alias}: backend {m.backend!r}")
    for role, stances in roles.items():
        missing = set(STANCES) - set(stances)
        if missing:
            raise V2ConfigError(f"role {role} missing {sorted(missing)}")
    return V2Config(models=models, judges=judges, roles=roles)
