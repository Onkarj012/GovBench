from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

ROLES = ("magistrate", "ias", "procurement")
PRESSURES = (
    "authority",
    "bribe",
    "threat",
    "sympathy",
    "deadline",
    "bandwagon",
    "legal_but_wrong",
    "slow_burn",
    "identity",
)
SPLITS = ("public", "private")
TIERS = ("standard", "hard")
REVIEW_STATUSES = ("draft", "source_checked", "verified", "disputed")
PUBLISHABLE_STATUSES = ("source_checked", "verified")

_ID_RE = re.compile(r"^(MAG|IAS|PROC)-[A-Z0-9]+-[A-Z_]+-\d{3}$")
_OPTION_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_VAR_RE = re.compile(r"\{(\w+)\}")


class ScenarioV2Error(Exception):
    """Raised when a v2 scenario file is invalid."""


@dataclass(frozen=True)
class PressureTurn:
    speaker: str
    text: str
    intensity: int


@dataclass(frozen=True)
class AnswerKey:
    decision: str
    legal_basis: tuple[str, ...]
    notes: str
    # Every defensible turn-0 decision; just (decision,) unless grey.
    acceptable: tuple[str, ...] = ()


@dataclass(frozen=True)
class ControlTurn:
    """A turn with new, legally relevant facts where changing is correct."""

    speaker: str
    text: str
    expected: str
    rationale: str


@dataclass(frozen=True)
class ScenarioV2:
    id: str
    role: str
    decision_type: str
    pressure: str
    difficulty: str
    split: str
    tier: str
    canary: str
    case_template: str
    fact_space: dict | None
    options: tuple[str, ...]
    neutral_options: tuple[str, ...]
    answer_key: AnswerKey
    pressure_direction: str
    pressure_turns: tuple[PressureTurn, ...]
    escalate_keywords: tuple[str, ...]
    review_status: str
    source_path: str
    control: ControlTurn | None = None

    @property
    def publishable(self) -> bool:
        """True when the scenario may appear in a public export."""
        return (
            self.split == "public"
            and self.review_status in PUBLISHABLE_STATUSES
        )


def load_v2_scenario(path: Path) -> ScenarioV2:
    """Parse and validate one v2 scenario JSON file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScenarioV2Error(f"{path}: cannot read JSON: {exc}") from exc
    try:
        return _parse(raw, path)
    except (KeyError, TypeError, ValueError) as exc:
        raise ScenarioV2Error(f"{path}: {exc!r}") from exc


def load_v2_folder(folder: Path) -> list[ScenarioV2]:
    """Load every v2 scenario under folder, sorted by id."""
    files = sorted(folder.rglob("*.json"))
    scenarios = [load_v2_scenario(f) for f in files]
    seen: dict[str, str] = {}
    for s in scenarios:
        if s.id in seen:
            raise ScenarioV2Error(
                f"duplicate id {s.id} in {s.source_path} and {seen[s.id]}"
            )
        seen[s.id] = s.source_path
    return sorted(scenarios, key=lambda s: s.id)


def _parse(raw: dict, path: Path) -> ScenarioV2:
    """Build a ScenarioV2 from raw JSON and enforce every schema rule."""
    sid = str(raw["id"])
    errors: list[str] = []
    if raw.get("version") != "v2":
        errors.append("version must be 'v2'")
    if not _ID_RE.match(sid):
        errors.append(f"id {sid!r} must match ROLE-DECISION-PRESSURE-NNN")
    role = str(raw["role"])
    if role not in ROLES:
        errors.append(f"role {role!r} not in {ROLES}")
    pressure = str(raw["pressure"])
    if pressure not in PRESSURES:
        errors.append(f"pressure {pressure!r} not in {PRESSURES}")
    split = str(raw.get("split", "public"))
    if split not in SPLITS:
        errors.append(f"split {split!r} not in {SPLITS}")
    tier = str(raw.get("tier", "standard"))
    if tier not in TIERS:
        errors.append(f"tier {tier!r} not in {TIERS}")
    canary = str(raw.get("canary", ""))
    if canary != f"GOVBENCH-CANARY-{sid}":
        errors.append("canary must be GOVBENCH-CANARY-<id>")

    fmt = raw["decision_format"]
    options = tuple(str(o) for o in fmt["options"])
    neutral = tuple(str(o) for o in fmt.get("neutral", []))
    if len(options) < 2 or len(set(options)) != len(options):
        errors.append("decision_format.options needs 2+ unique options")
    for o in options:
        if not _OPTION_RE.match(o):
            errors.append(f"option {o!r} must be snake_case")
    for o in neutral:
        if o not in options:
            errors.append(f"neutral option {o!r} not in options")

    ak = raw["answer_key"]
    answer = AnswerKey(
        decision=str(ak["decision"]),
        legal_basis=tuple(str(b) for b in ak.get("legal_basis", [])),
        notes=str(ak.get("notes", "")),
        acceptable=tuple(
            str(o) for o in ak.get("acceptable", [ak["decision"]])
        ),
    )
    if answer.decision not in options:
        errors.append(f"answer_key.decision {answer.decision!r} not in options")
    if answer.decision not in answer.acceptable:
        errors.append("answer_key.acceptable must include the decision")
    for o in answer.acceptable:
        if o not in options:
            errors.append(f"acceptable option {o!r} not in options")
    if not answer.legal_basis:
        errors.append("answer_key.legal_basis must cite at least one source")

    direction = str(raw["pressure_direction"])
    if direction not in options:
        errors.append(f"pressure_direction {direction!r} not in options")
    if direction == answer.decision:
        errors.append("pressure_direction must differ from answer_key")

    turns = tuple(
        PressureTurn(
            speaker=str(t["speaker"]),
            text=str(t["text"]),
            intensity=int(t.get("intensity", 1)),
        )
        for t in raw["pressure_turns"]
    )
    if not 2 <= len(turns) <= 5:
        errors.append("pressure_turns must have 2-5 turns")

    control = None
    if "control" in raw:
        c = raw["control"]
        control = ControlTurn(
            speaker=str(c["speaker"]),
            text=str(c["text"]),
            expected=str(c["expected"]),
            rationale=str(c.get("rationale", "")),
        )
        if control.expected not in options:
            errors.append(
                f"control.expected {control.expected!r} not in options"
            )
        if control.expected == answer.decision:
            errors.append("control.expected must differ from answer_key")
        if not control.rationale:
            errors.append("control.rationale must explain the change")
    if tier == "hard" and control is None:
        errors.append("hard tier scenarios need a control turn")

    case_template = str(raw["case_template"])
    fact_space = raw.get("fact_space")
    declared = {f["name"] for f in (fact_space or {}).get("fields", [])}
    used = set(_VAR_RE.findall(case_template))
    for t in turns:
        used |= set(_VAR_RE.findall(t.text))
    if control is not None:
        used |= set(_VAR_RE.findall(control.text))
    missing = used - declared
    if missing:
        errors.append(f"undeclared template vars: {sorted(missing)}")

    review = raw.get("review", {})
    status = str(review.get("status", "draft"))
    if status not in REVIEW_STATUSES:
        errors.append(f"review.status {status!r} not in {REVIEW_STATUSES}")

    if errors:
        raise ValueError("; ".join(errors))

    return ScenarioV2(
        id=sid,
        role=role,
        decision_type=str(raw["decision_type"]),
        pressure=pressure,
        difficulty=str(raw.get("difficulty", "medium")),
        split=split,
        tier=tier,
        canary=canary,
        case_template=case_template,
        fact_space=fact_space,
        options=options,
        neutral_options=neutral,
        answer_key=answer,
        pressure_direction=direction,
        pressure_turns=turns,
        escalate_keywords=tuple(
            str(k)
            for k in raw.get("classifier_hints", {}).get(
                "escalate_keywords", []
            )
        ),
        review_status=status,
        source_path=str(path),
        control=control,
    )
