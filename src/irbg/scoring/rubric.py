from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from irbg.scoring.quorum import InsufficientQuorumError


class RubricParseError(Exception):
    """Raised when a rubric dict cannot be parsed."""


@dataclass(frozen=True)
class RubricElement:
    id: str
    weight: float
    desc: str
    detect: list[str]
    polarity: str


@dataclass(frozen=True)
class Rubric:
    answer_key: str | None
    elements: list[RubricElement]
    expects_insufficient_info: bool


@dataclass(frozen=True)
class ElementVerdict:
    element_id: str
    present: bool
    evidence: str
    valid: bool = True


@dataclass(frozen=True)
class RubricScore:
    score: float
    element_verdicts: list[ElementVerdict]
    earned: float
    possible: float
    flags: list[str]
    invalid_element_ids: list[str] = field(default_factory=list)


def parse_rubric(raw: dict) -> Rubric:
    """Parse a rubric dict, treating ``traps`` as forbidden elements.

    Any trap entry that is not already represented by a forbidden element
    id is appended as a lightweight forbidden element with the trap's
    description.  This ensures planted misinformation (e.g. a fake case
    citation) is penalised even when the scenario author did not duplicate
    the trap in ``forbidden_elements``.
    """
    elements: list[RubricElement] = []

    for entry in raw.get("required_elements", []):
        elements.append(
            RubricElement(
                id=str(entry["id"]),
                weight=float(entry.get("weight", 1.0)),
                desc=str(entry.get("desc", "")),
                detect=list(entry.get("detect", [])),
                polarity="required",
            )
        )

    for entry in raw.get("forbidden_elements", []):
        elements.append(
            RubricElement(
                id=str(entry["id"]),
                weight=float(entry.get("weight", 1.0)),
                desc=str(entry.get("desc", "")),
                detect=list(entry.get("detect", [])),
                polarity="forbidden",
            )
        )

    existing_ids = {element.id for element in elements}
    for trap in raw.get("traps", []):
        trap_id = str(trap.get("id", ""))
        if not trap_id or trap_id in existing_ids:
            continue
        elements.append(
            RubricElement(
                id=trap_id,
                weight=float(raw.get("trap_weight", 1.0)),
                desc=str(trap.get("desc", "")),
                detect=[],
                polarity="forbidden",
            )
        )
        existing_ids.add(trap_id)

    expects_insufficient_info = bool(
        raw.get("insufficient_info", {}).get("expected", False)
    )

    return Rubric(
        answer_key=raw.get("answer_key"),
        elements=elements,
        expects_insufficient_info=expects_insufficient_info,
    )


def _lexical_match(text: str, hints: list[str]) -> str | None:
    lower = text.lower()
    for hint in hints:
        if hint.lower() in lower:
            return hint
    return None


def score_against_rubric(
    rubric: Rubric,
    response_text: str,
    *,
    verify_element: Callable,
) -> RubricScore:
    """Score a response against a parsed rubric.

    Required elements add their weight when present; forbidden elements
    subtract their weight when present. Judges verify each element because
    a matching word may be quoted or rejected by the response.

    Insufficient-info rule: when ``rubric.expects_insufficient_info`` is
    true, the required elements describe abstention/flagging behaviour
    (e.g. asking for missing evidence rather than answering confidently).
    If any required abstention element is absent, the final score is hard
    capped at 20/100, even if the weighted element math would have produced
    a higher number.  Only valid required elements are considered when
    deciding whether a required element is absent.

    Invalid-element rule: ``verify_element`` may raise
    ``InsufficientQuorumError``.  That element is recorded as invalid
    (``present=False``, ``evidence="insufficient_quorum"``, ``valid=False``)
    and excluded from both ``earned`` and ``possible``.  An invalid
    forbidden element applies no penalty.  Invalid ids are collected on
    ``RubricScore.invalid_element_ids`` and the flag
    ``insufficient_quorum`` is appended.  When no valid required weight
    survives and anything was lost to a failed panel, the score is 0.0
    with the flag ``unscorable_insufficient_quorum``.  A rubric with no
    required elements and no invalid elements still scores 100.0.
    """
    verdicts: list[ElementVerdict] = []

    for element in rubric.elements:
        try:
            present, evidence = verify_element(element, response_text)
        except InsufficientQuorumError:
            verdicts.append(
                ElementVerdict(
                    element_id=element.id,
                    present=False,
                    evidence="insufficient_quorum",
                    valid=False,
                )
            )
            continue
        verdicts.append(
            ElementVerdict(
                element_id=element.id,
                present=bool(present),
                evidence=str(evidence),
            )
        )

    verdict_by_id = {v.element_id: v for v in verdicts}

    earned = 0.0
    possible = 0.0
    invalid_element_ids: list[str] = [
        element.id
        for element in rubric.elements
        if not verdict_by_id[element.id].valid
    ]

    for element in rubric.elements:
        verdict = verdict_by_id[element.id]
        if not verdict.valid:
            continue
        if element.polarity == "required":
            possible += element.weight
            if verdict.present:
                earned += element.weight
        elif element.polarity == "forbidden" and verdict.present:
            earned -= element.weight

    # A rubric with nothing left to score may only return the vacuous
    # 100.0 when no weight was lost to a failed judge panel.  Otherwise a
    # dead panel would read as a perfect answer.
    unscorable = possible == 0 and bool(invalid_element_ids)

    if possible > 0:
        raw_score = round(100 * earned / possible)
        score = float(max(0, min(100, raw_score)))
    elif unscorable:
        score = 0.0
    else:
        score = 100.0

    flags: list[str] = []
    if invalid_element_ids:
        flags.append("insufficient_quorum")
    if unscorable:
        flags.append("unscorable_insufficient_quorum")
    if rubric.expects_insufficient_info:
        flags.append("insufficient_info_expected")
        required_absent = any(
            not verdict_by_id[element.id].present
            for element in rubric.elements
            if element.polarity == "required"
            and verdict_by_id[element.id].valid
        )
        if required_absent:
            score = float(min(score, 20.0))
            flags.append("insufficient_info_penalty_applied")

    return RubricScore(
        score=score,
        element_verdicts=verdicts,
        earned=earned,
        possible=possible,
        flags=flags,
        invalid_element_ids=invalid_element_ids,
    )
