from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from irbg.scoring import judge
from irbg.scoring.quorum import InsufficientQuorumError


@dataclass(frozen=True)
class StubResponse:
    success: bool
    text: str = ""
    error: str | None = None


class StubClient:
    def __init__(self, responses: list[StubResponse]) -> None:
        self.responses = responses
        self.calls = 0

    def chat(self, **_kwargs: object) -> StubResponse:
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return response


def _score_response(score: int) -> StubResponse:
    return StubResponse(
        success=True,
        text=(f'{{"score": {score}, "reasoning": "sound", "flags": []}}'),
    )


def test_judge_response_accepts_quorum(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        judge,
        "_select_judges",
        lambda _model_alias: (
            ("gpt-4o", "openai"),
            ("claude-sonnet-4.6", "anthropic"),
        ),
    )
    client = StubClient([_score_response(80), _score_response(60)])

    result = judge.judge_response(
        pillar="p2_procedural_integrity",
        scenario_context="context",
        response_text="response",
        client=client,
    )

    assert result.score == 70.0
    assert result.judges == ["gpt-4o", "claude-sonnet-4.6"]


def test_judge_response_raises_when_quorum_is_short(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        judge,
        "_select_judges",
        lambda _model_alias: (("gpt-4o", "openai"),),
    )
    client = StubClient(
        [StubResponse(success=False, error="temporary failure")]
    )

    with pytest.raises(InsufficientQuorumError, match="gpt-4o"):
        judge.judge_response(
            pillar="p2_procedural_integrity",
            scenario_context="context",
            response_text="response",
            client=client,
        )


def test_element_judges_raise_on_tie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        judge,
        "_select_judges",
        lambda _model_alias: (
            ("gpt-4o", "openai"),
            ("claude-sonnet-4.6", "anthropic"),
        ),
    )
    client = StubClient(
        [
            StubResponse(success=True, text='{"present": true}'),
            StubResponse(success=True, text='{"present": false}'),
        ]
    )

    with pytest.raises(InsufficientQuorumError, match="tied"):
        judge.verify_element_with_judge(
            SimpleNamespace(id="element-1", desc="The element"),
            "response",
            pillar="p2_procedural_integrity",
            client=client,
        )


def test_judge_retries_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        judge,
        "_select_judges",
        lambda _model_alias: (
            ("gpt-4o", "openai"),
            ("claude-sonnet-4.6", "anthropic"),
        ),
    )
    client = StubClient(
        [
            StubResponse(success=False, error="temporary failure"),
            StubResponse(success=True, text="not JSON"),
            _score_response(90),
            _score_response(70),
        ]
    )

    result = judge.judge_response(
        pillar="p2_procedural_integrity",
        scenario_context="context",
        response_text="response",
        client=client,
    )

    assert result.score == 80.0
    assert client.calls == 4
