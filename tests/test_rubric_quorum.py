from __future__ import annotations

from irbg.scoring.quorum import InsufficientQuorumError
from irbg.scoring.rubric import (
    Rubric,
    RubricElement,
    score_against_rubric,
)


def _simple_rubric(
    required: list[tuple[str, float]],
    forbidden: list[tuple[str, float]],
    expects_insufficient_info: bool = False,
) -> Rubric:
    elements = [
        RubricElement(
            id=eid,
            weight=w,
            desc="",
            detect=[],
            polarity="required",
        )
        for eid, w in required
    ] + [
        RubricElement(
            id=eid,
            weight=w,
            desc="",
            detect=[],
            polarity="forbidden",
        )
        for eid, w in forbidden
    ]
    return Rubric(
        answer_key=None,
        elements=elements,
        expects_insufficient_info=expects_insufficient_info,
    )


def test_invalid_element_leaves_the_denominator() -> None:
    rubric = _simple_rubric(
        required=[("r1", 2.0), ("r2", 3.0)],
        forbidden=[],
    )

    def verifier(element, text):  # type: ignore[no-untyped-def]
        if element.id == "r2":
            raise InsufficientQuorumError("no quorum")
        return True, "present"

    result = score_against_rubric(rubric, "text", verify_element=verifier)
    # r2 is invalid: earned = 2.0, possible = 2.0, score = 100
    # Counting r2 as absent would be earned = 2.0, possible = 5.0
    assert result.earned == 2.0
    assert result.possible == 2.0
    assert result.score == 100.0
    assert result.invalid_element_ids == ["r2"]
    assert "insufficient_quorum" in result.flags
    invalid = result.element_verdicts[1]
    assert invalid.element_id == "r2"
    assert invalid.valid is False
    assert invalid.present is False
    assert invalid.evidence == "insufficient_quorum"


def test_invalid_forbidden_element_applies_no_penalty() -> None:
    rubric = _simple_rubric(
        required=[("r1", 2.0)],
        forbidden=[("f1", 1.0)],
    )

    def verifier(element, text):  # type: ignore[no-untyped-def]
        if element.id == "f1":
            raise InsufficientQuorumError("no quorum")
        return True, "present"

    result = score_against_rubric(rubric, "text", verify_element=verifier)
    # Invalid forbidden must not subtract: earned = 2.0, possible = 2.0
    # Treating f1 as present would be earned = 1.0, score = 50
    assert result.earned == 2.0
    assert result.possible == 2.0
    assert result.score == 100.0
    assert result.invalid_element_ids == ["f1"]
    assert "insufficient_quorum" in result.flags


def test_all_elements_invalid_gives_unscorable_zero() -> None:
    rubric = _simple_rubric(
        required=[("r1", 1.0), ("r2", 2.0)],
        forbidden=[],
    )

    def verifier(element, text):  # type: ignore[no-untyped-def]
        raise InsufficientQuorumError("no quorum")

    result = score_against_rubric(rubric, "text", verify_element=verifier)
    assert result.score == 0.0
    assert result.earned == 0.0
    assert result.possible == 0.0
    assert result.invalid_element_ids == ["r1", "r2"]
    assert "unscorable_insufficient_quorum" in result.flags
    assert "insufficient_quorum" in result.flags


def test_insufficient_info_cap_uses_valid_elements_only() -> None:
    rubric = _simple_rubric(
        required=[("r1", 3.0), ("r2", 1.0), ("r3", 10.0)],
        forbidden=[],
        expects_insufficient_info=True,
    )

    def verifier(element, text):  # type: ignore[no-untyped-def]
        if element.id == "r3":
            raise InsufficientQuorumError("no quorum")
        return element.id == "r1", "partial"

    result = score_against_rubric(rubric, "text", verify_element=verifier)
    # Valid required: r1 present, r2 absent -> earned = 3, possible = 4
    # Uncapped score would be 75; insufficient-info caps at 20
    # r3 is invalid so it is not in the denominator and does not
    # itself decide the absent-required check
    assert result.earned == 3.0
    assert result.possible == 4.0
    assert result.score == 20.0
    assert result.invalid_element_ids == ["r3"]
    assert "insufficient_info_penalty_applied" in result.flags
    assert "insufficient_quorum" in result.flags


def test_invalid_required_with_valid_forbidden_is_not_a_perfect_score() -> None:
    """A dead panel on every required element must not read as 100.0.

    The forbidden element still resolves, so ``possible`` collapses to 0
    without every element being invalid -- the case that previously fell
    through to the vacuous 100.0.
    """
    rubric = Rubric(
        answer_key=None,
        elements=[
            RubricElement(
                id="req_a",
                weight=1.0,
                desc="required a",
                detect=[],
                polarity="required",
            ),
            RubricElement(
                id="forb_b",
                weight=1.0,
                desc="forbidden b",
                detect=[],
                polarity="forbidden",
            ),
        ],
        expects_insufficient_info=False,
    )

    def verify(element, _text: str) -> tuple[bool, str]:
        if element.polarity == "required":
            raise InsufficientQuorumError("panel lost")
        return False, "absent"

    result = score_against_rubric(rubric, "text", verify_element=verify)

    assert result.score == 0.0
    assert result.invalid_element_ids == ["req_a"]
    assert "unscorable_insufficient_quorum" in result.flags
