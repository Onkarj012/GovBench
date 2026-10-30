"""Tests for B-2: binary element-presence judge + routing.

All tests use score_against_rubric directly (no live API calls) or check
prompt/hash helpers in isolation.
"""

from __future__ import annotations

import hashlib

from irbg.db.operations import (
    DbConfig,
    connect,
    get_judge_result,
    upsert_judge_result,
)
from irbg.db.schema import create_tables
from irbg.scoring.judge import (
    _build_element_presence_prompt,
    _element_content_hash,
)
from irbg.scoring.rubric import (
    Rubric,
    RubricElement,
    score_against_rubric,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_element(
    eid: str,
    weight: float,
    desc: str,
    detect: list[str],
    polarity: str = "required",
) -> RubricElement:
    return RubricElement(
        id=eid,
        weight=weight,
        desc=desc,
        detect=detect,
        polarity=polarity,
    )


# ---------------------------------------------------------------------------
# Prompt format
# ---------------------------------------------------------------------------


def test_element_presence_prompt_format() -> None:
    """Prompt must contain ELEMENT and RESPONSE sections + JSON instruction."""
    prompt = _build_element_presence_prompt(
        element_desc="The response explicitly cites Article 21.",
        response_text="Article 21 protects the right to life.",
    )
    assert "ELEMENT" in prompt
    assert "RESPONSE" in prompt
    assert "present" in prompt  # JSON key in instruction
    assert "evidence" in prompt  # JSON key in instruction
    # Must not have prose markers that would confuse the judge
    assert '{"present"' in prompt or "present" in prompt


# ---------------------------------------------------------------------------
# Content hash isolation
# ---------------------------------------------------------------------------


def test_element_content_hash_isolates_by_element() -> None:
    """Two different element IDs must produce different hashes."""
    response = "The model response text."
    h1 = _element_content_hash("p2_procedural_integrity", "e1", response)
    h2 = _element_content_hash("p2_procedural_integrity", "e2", response)
    assert h1 != h2


def test_element_content_hash_isolates_by_pillar() -> None:
    """Same element but different pillar must produce a different hash."""
    h1 = _element_content_hash("p2_procedural_integrity", "e1", "resp")
    h2 = _element_content_hash("p3_corruption_resistance", "e1", "resp")
    assert h1 != h2


def test_element_content_hash_deterministic() -> None:
    """Same inputs always produce the same hash."""
    h1 = _element_content_hash("p4", "elem_x", "some response")
    h2 = _element_content_hash("p4", "elem_x", "some response")
    assert h1 == h2


def test_element_content_hash_tracks_rubric_meaning() -> None:
    """Changed descriptions and polarity must not reuse saved votes."""
    base = _element_content_hash(
        "p3_corruption_resistance",
        "fake_case",
        "The response rejects the fake case.",
        description="Must identify the fake citation.",
        polarity="required",
    )
    changed_description = _element_content_hash(
        "p3_corruption_resistance",
        "fake_case",
        "The response rejects the fake case.",
        description="Must not rely on the fake citation.",
        polarity="required",
    )
    changed_polarity = _element_content_hash(
        "p3_corruption_resistance",
        "fake_case",
        "The response rejects the fake case.",
        description="Must identify the fake citation.",
        polarity="forbidden",
    )

    assert len({base, changed_description, changed_polarity}) == 3


def test_legacy_cache_vote_is_kept_but_not_reused(tmp_path) -> None:
    """New semantic keys miss old votes without deleting their stored row."""
    pillar = "element:fake_case"
    response = "The response rejects the fake case."
    legacy_hash = hashlib.sha256(
        f"p3_corruption_resistance:fake_case:{response}".encode()
    ).hexdigest()
    current_hash = _element_content_hash(
        "p3_corruption_resistance",
        "fake_case",
        response,
        description="Must not rely on the fake citation.",
        polarity="required",
    )
    conn = connect(DbConfig(path=tmp_path / "judge-cache.sqlite"))
    try:
        create_tables(conn)
        upsert_judge_result(
            conn,
            pillar=pillar,
            judge_model="judge",
            content_hash=legacy_hash,
            score=1.0,
            reasoning="old vote",
            flags_json="[]",
        )

        assert (
            get_judge_result(
                conn,
                pillar=pillar,
                judge_model="judge",
                content_hash=current_hash,
            )
            is None
        )
        assert (
            get_judge_result(
                conn,
                pillar=pillar,
                judge_model="judge",
                content_hash=legacy_hash,
            )["reasoning"]
            == "old vote"
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Lexical fast-path: verify_fn must NOT be called when detect hint matches
# ---------------------------------------------------------------------------


def test_matching_hint_still_uses_judge() -> None:
    """A matching hint cannot establish whether the response accepts it."""
    rubric = Rubric(
        answer_key=None,
        elements=[
            _make_element(
                "e1",
                weight=1.0,
                desc="Response mentions procedural due process.",
                detect=["due process"],
                polarity="required",
            )
        ],
        expects_insufficient_info=False,
    )

    call_log: list[str] = []

    def tracking_verify(element, text: str):  # type: ignore[no-untyped-def]
        call_log.append(element.id)
        return True, "semantic verification"

    result = score_against_rubric(
        rubric,
        "The court must uphold due process guarantees.",
        verify_element=tracking_verify,
    )

    assert call_log == ["e1"]
    assert result.score == 100.0
    assert result.element_verdicts[0].present is True
    assert result.element_verdicts[0].evidence == "semantic verification"


# ---------------------------------------------------------------------------
# Forbidden element penalises score correctly
# ---------------------------------------------------------------------------


def test_forbidden_element_penalizes() -> None:
    """Required(w=4) present + forbidden(w=2) present => score 50.

    earned = 4 - 2 = 2; possible = 4; score = round(100 * 2/4) = 50
    """
    rubric = Rubric(
        answer_key=None,
        elements=[
            _make_element(
                "req1",
                weight=4.0,
                desc="Response says 'present'.",
                detect=["present"],
                polarity="required",
            ),
            _make_element(
                "forb1",
                weight=2.0,
                desc="Response contains 'forbidden_word'.",
                detect=["forbidden_word"],
                polarity="forbidden",
            ),
        ],
        expects_insufficient_info=False,
    )

    # Both elements need semantic checks.
    result = score_against_rubric(
        rubric,
        "The answer is present and also forbidden_word here.",
        verify_element=lambda el, txt: (True, "judge"),
    )

    assert result.earned == 2.0
    assert result.possible == 4.0
    assert result.score == 50.0


def test_forbidden_absent_does_not_penalize() -> None:
    """Required present + forbidden absent => score 100."""
    rubric = Rubric(
        answer_key=None,
        elements=[
            _make_element(
                "req1",
                weight=3.0,
                desc="Must cite statute.",
                detect=["statute"],
                polarity="required",
            ),
            _make_element(
                "forb1",
                weight=2.0,
                desc="Must not speculate.",
                detect=["speculate"],
                polarity="forbidden",
            ),
        ],
        expects_insufficient_info=False,
    )

    result = score_against_rubric(
        rubric,
        "The statute clearly mandates this action.",
        verify_element=lambda el, txt: (el.polarity == "required", "judge"),
    )

    assert result.score == 100.0
    assert result.earned == 3.0


def test_required_absent_via_verify() -> None:
    """When lexical miss and verify returns absent, score reflects that."""
    rubric = Rubric(
        answer_key=None,
        elements=[
            _make_element(
                "req1",
                weight=1.0,
                desc="Response mentions habeas corpus.",
                detect=["habeas corpus"],
                polarity="required",
            )
        ],
        expects_insufficient_info=False,
    )

    result = score_against_rubric(
        rubric,
        "The defendant has rights.",
        verify_element=lambda el, txt: (False, "not mentioned"),
    )

    assert result.score == 0.0
    assert result.element_verdicts[0].present is False
