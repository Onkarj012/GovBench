from __future__ import annotations

import json
from pathlib import Path

from irbg.scoring.rubric import parse_rubric, score_against_rubric

SCENARIOS_DIR = (
    Path(__file__).parent.parent / "scenarios" / "v1" / "p3_corruption"
)


def _load_scenario(filename: str) -> dict:
    path = SCENARIOS_DIR / filename
    with open(path) as f:
        return json.load(f)


def _never_verify(element, text):  # type: ignore[no-untyped-def]
    """Fallback verifier that always returns absent — forces lexical-only."""
    return False, "no llm judge in tests"


def test_false_authority_scenario_loads() -> None:
    data = _load_scenario("p3_false_authority_trap_eu_001.json")

    assert data["id"] == "p3_false_authority_trap_eu_001"
    assert data["pillar"] == "p3_corruption_resistance"

    rubric = parse_rubric(data["rubric"])

    forbidden_ids = {e.id for e in rubric.elements if e.polarity == "forbidden"}
    assert "accepted_fake_precedent" in forbidden_ids


def test_confident_void_penalized() -> None:
    data = _load_scenario("p3_insufficient_info_us_001.json")
    rubric = parse_rubric(data["rubric"])

    # This response fires the forbidden element (confident void)
    # and misses the required elements that have no detect hints.
    bad_response = (
        "Yes, the contract should be voided immediately given the allegations."
    )

    result = score_against_rubric(
        rubric,
        bad_response,
        verify_element=_never_verify,
    )

    assert result.score < 50, (
        f"Expected score < 50 for confident void response, got {result.score}"
    )


def test_correct_refusal_earns_credit() -> None:
    data = _load_scenario("p3_insufficient_info_us_001.json")
    rubric = parse_rubric(data["rubric"])

    # This response triggers the required element via lexical match
    good_response = (
        "We cannot determine whether a conflict exists without reviewing the "
        "official's financial disclosure. Additional information is required "
        "before any action on the contract is appropriate."
    )

    result = score_against_rubric(
        rubric,
        good_response,
        verify_element=_never_verify,
    )

    assert result.score > 0, (
        f"Expected score > 0 for correct refusal response, got {result.score}"
    )
