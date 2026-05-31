from __future__ import annotations

from irbg.config import ModelConfig
from irbg.scoring import judge


def _cfg(**kw) -> ModelConfig:
    base = dict(
        alias="gpt-4o",
        name="GPT-4o",
        provider="openrouter",
        model_id="openai/gpt-4o",
        max_tokens=512,
        temperature=0.0,
    )
    base.update(kw)
    return ModelConfig(**base)


def test_fingerprint_falls_back_to_model_id(monkeypatch) -> None:
    judge._judge_fingerprint.cache_clear()
    monkeypatch.setattr(judge, "get_model_config", lambda alias: _cfg())
    assert judge._judge_fingerprint("gpt-4o") == "gpt-4o@openai/gpt-4o"


def test_fingerprint_uses_pinned_version(monkeypatch) -> None:
    judge._judge_fingerprint.cache_clear()
    monkeypatch.setattr(
        judge, "get_model_config", lambda alias: _cfg(version="2026-05-01")
    )
    assert judge._judge_fingerprint("gpt-4o") == "gpt-4o@2026-05-01"
    judge._judge_fingerprint.cache_clear()
