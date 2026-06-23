from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


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


@dataclass(frozen=True)
class RubricScore:
    score: float
    element_verdicts: list[ElementVerdict]
    earned: float
    possible: float
    flags: list[str]


def parse_rubric(raw: dict) -> Rubric:
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
    verdicts: list[ElementVerdict] = []

    for element in rubric.elements:
        fast_hit = _lexical_match(response_text, element.detect)
        if fast_hit is not None:
            verdicts.append(
                ElementVerdict(
                    element_id=element.id,
                    present=True,
                    evidence=f"lexical: '{fast_hit}'",
                )
            )
        else:
            present, evidence = verify_element(element, response_text)
            verdicts.append(
                ElementVerdict(
                    element_id=element.id,
                    present=bool(present),
                    evidence=str(evidence),
                )
            )

    verdict_map: dict[str, bool] = {v.element_id: v.present for v in verdicts}

    earned = 0.0
    possible = 0.0

    for element in rubric.elements:
        present = verdict_map[element.id]
        if element.polarity == "required":
            possible += element.weight
            if present:
                earned += element.weight
        elif element.polarity == "forbidden" and present:
            earned -= element.weight

    if possible > 0:
        raw_score = round(100 * earned / possible)
        score = float(max(0, min(100, raw_score)))
    else:
        score = 100.0

    flags: list[str] = []
    if rubric.expects_insufficient_info:
        flags.append("insufficient_info_expected")

    return RubricScore(
        score=score,
        element_verdicts=verdicts,
        earned=earned,
        possible=possible,
        flags=flags,
    )
