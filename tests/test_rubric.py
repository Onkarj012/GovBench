from __future__ import annotations

from irbg.scoring.rubric import (
    Rubric,
    RubricElement,
    score_against_rubric,
)


def _never_called(element, text):  # type: ignore[no-untyped-def]
    raise AssertionError("verify_element should not have been called")


def _always_present(element, text):  # type: ignore[no-untyped-def]
    return True, "mocked present"


def _always_absent(element, text):  # type: ignore[no-untyped-def]
    return False, "mocked absent"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_all_required_present_scores_100() -> None:
    rubric = _simple_rubric(required=[("r1", 1.0), ("r2", 2.0)], forbidden=[])
    result = score_against_rubric(
        rubric, "some response", verify_element=_always_present
    )
    assert result.score == 100.0
    assert result.earned == 3.0
    assert result.possible == 3.0


def test_forbidden_present_penalizes() -> None:
    rubric = _simple_rubric(
        required=[("r1", 2.0)],
        forbidden=[("f1", 1.0)],
    )

    call_log: list[str] = []

    def verifier(element, text):  # type: ignore[no-untyped-def]
        call_log.append(element.id)
        if element.polarity == "required":
            return True, "ok"
        return True, "forbidden present"

    result = score_against_rubric(rubric, "text", verify_element=verifier)
    # earned = 2.0 (required) - 1.0 (forbidden) = 1.0; possible = 2.0
    # score = round(100 * 1.0 / 2.0) = 50
    assert result.earned == 1.0
    assert result.score == 50.0


def test_lexical_fast_path_no_verify_call() -> None:
    rubric = Rubric(
        answer_key=None,
        elements=[
            RubricElement(
                id="e1",
                weight=1.0,
                desc="",
                detect=["keyword"],
                polarity="required",
            )
        ],
        expects_insufficient_info=False,
    )
    result = score_against_rubric(
        rubric,
        "this text contains keyword clearly",
        verify_element=_never_called,
    )
    assert result.score == 100.0
    assert result.element_verdicts[0].present is True
    assert "lexical" in result.element_verdicts[0].evidence


def test_missing_required_drops_by_weight() -> None:
    rubric = _simple_rubric(required=[("r1", 3.0), ("r2", 1.0)], forbidden=[])

    def verifier(element, text):  # type: ignore[no-untyped-def]
        return element.id == "r2", "partial"

    result = score_against_rubric(rubric, "text", verify_element=verifier)
    # earned = 1.0, possible = 4.0 => score = round(100 * 0.25) = 25
    assert result.earned == 1.0
    assert result.possible == 4.0
    assert result.score == 25.0


def test_score_clamps_to_zero() -> None:
    # Only forbidden elements, no required -> possible=0 -> score=100 sentinel
    # But if we have required + heavy forbidden that makes earned negative:
    rubric = _simple_rubric(
        required=[("r1", 1.0)],
        forbidden=[("f1", 5.0)],
    )

    def verifier(element, text):  # type: ignore[no-untyped-def]
        return True, "present"

    result = score_against_rubric(rubric, "text", verify_element=verifier)
    # earned = 1.0 - 5.0 = -4.0; possible = 1.0
    # raw_score = round(100 * -4) = -400 -> clamped to 0
    assert result.score == 0.0


def test_expects_insufficient_info_flag() -> None:
    rubric = _simple_rubric(
        required=[],
        forbidden=[],
        expects_insufficient_info=True,
    )
    result = score_against_rubric(
        rubric, "I don't have enough information", verify_element=_always_absent
    )
    assert "insufficient_info_expected" in result.flags
