from __future__ import annotations

import datetime
import hashlib
import random
import re
from dataclasses import dataclass


class FactGenerationError(Exception):
    """Raised when fact generation fails."""


@dataclass(frozen=True)
class FactField:
    name: str
    kind: str
    spec: dict


@dataclass(frozen=True)
class FactSpace:
    fields: list[FactField]
    max_instances: int | None = None


_KIND_MAP = {
    "choice": "choice",
    "int": "int",
    "pattern": "pattern",
    "date": "date",
    "name": "name",
}


def parse_fact_space(raw: dict) -> FactSpace:
    raw_fields = raw.get("fields", [])
    parsed: list[FactField] = []
    for entry in raw_fields:
        if "type" not in entry:
            raise FactGenerationError(
                f"Fact field is missing required key 'type': {entry}"
            )
        kind_raw = entry["type"]
        if kind_raw not in _KIND_MAP:
            raise FactGenerationError(
                f"Unknown fact field type: '{kind_raw}'. "
                f"Allowed: {sorted(_KIND_MAP)}"
            )
        spec = {k: v for k, v in entry.items() if k not in ("name", "type")}
        parsed.append(
            FactField(
                name=str(entry.get("name", "")),
                kind=_KIND_MAP[kind_raw],
                spec=spec,
            )
        )
    max_instances = raw.get("max_instances")
    return FactSpace(fields=parsed, max_instances=max_instances)


def sample_instance(
    fact_space: FactSpace,
    *,
    rng: random.Random,
    draw_index: int = 0,
) -> dict:
    if (
        fact_space.max_instances is not None
        and draw_index >= fact_space.max_instances
    ):
        raise FactGenerationError(
            f"draw_index {draw_index} >= max_instances "
            f"{fact_space.max_instances}"
        )

    result: dict[str, object] = {}
    deferred: list[FactField] = []

    for ff in fact_space.fields:
        if ff.kind == "pattern":
            deferred.append(ff)
            continue
        result[ff.name] = _sample_scalar(ff, rng)

    for ff in deferred:
        result[ff.name] = _sample_pattern(ff, result)

    return result


def _sample_scalar(ff: FactField, rng: random.Random) -> object:
    if ff.kind == "choice":
        values = ff.spec["values"]
        weights = ff.spec.get("weights")
        if weights:
            return rng.choices(values, weights=weights, k=1)[0]
        return rng.choice(values)

    if ff.kind == "int":
        return rng.randint(int(ff.spec["min"]), int(ff.spec["max"]))

    if ff.kind == "date":
        start = datetime.date.fromisoformat(ff.spec["start"])
        end = datetime.date.fromisoformat(ff.spec["end"])
        delta = (end - start).days
        sampled = start + datetime.timedelta(days=rng.randint(0, delta))
        fmt = ff.spec.get("format", "%Y-%m-%d")
        return sampled.strftime(fmt)

    if ff.kind == "name":
        pool = ff.spec.get("pool", [])
        if not pool:
            raise FactGenerationError(
                f"Name field '{ff.name}' has an empty pool."
            )
        return rng.choice(pool)

    raise FactGenerationError(f"Unhandled scalar kind: '{ff.kind}'")


# Matches {name:width} or {name}
_PAT_TOKEN = re.compile(r"\{(\w+)(?::(\d+))?\}")


def _sample_pattern(ff: FactField, resolved: dict[str, object]) -> str:
    template: str = ff.spec["template"]

    def replacer(m: re.Match) -> str:
        var_name = m.group(1)
        width = m.group(2)
        value = resolved.get(var_name, "")
        if width is not None:
            return str(value).zfill(int(width))
        return str(value)

    return _PAT_TOKEN.sub(replacer, template)


def seed_for(template_id: str, run_seed: int) -> int:
    digest = hashlib.sha256(f"{template_id}:{run_seed}".encode()).digest()
    return int.from_bytes(digest[:8], "little")
