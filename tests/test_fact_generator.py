from __future__ import annotations

import random

import pytest

from irbg.engine.fact_generator import (
    FactField,
    FactGenerationError,
    FactSpace,
    sample_instance,
    seed_for,
)


def _make_rng(s: int = 0) -> random.Random:
    return random.Random(s)


# ---------------------------------------------------------------------------
# seed_for
# ---------------------------------------------------------------------------


def test_determinism_same_seed() -> None:
    fs = FactSpace(
        fields=[
            FactField(name="x", kind="int", spec={"min": 1, "max": 100}),
        ]
    )
    rng1 = _make_rng(99)
    rng2 = _make_rng(99)
    a = sample_instance(fs, rng=rng1)
    b = sample_instance(fs, rng=rng2)
    assert a == b


def test_independence_different_templates() -> None:
    s1 = seed_for("template_a", 42)
    s2 = seed_for("template_b", 42)
    assert s1 != s2


# ---------------------------------------------------------------------------
# choice
# ---------------------------------------------------------------------------


def test_choice_field() -> None:
    fs = FactSpace(
        fields=[
            FactField(
                name="color",
                kind="choice",
                spec={"values": ["red", "green", "blue"]},
            )
        ]
    )
    result = sample_instance(fs, rng=_make_rng(7))
    assert result["color"] in ("red", "green", "blue")


# ---------------------------------------------------------------------------
# int
# ---------------------------------------------------------------------------


def test_int_field_in_range() -> None:
    fs = FactSpace(
        fields=[FactField(name="n", kind="int", spec={"min": 10, "max": 20})]
    )
    for seed in range(20):
        result = sample_instance(fs, rng=_make_rng(seed))
        assert 10 <= result["n"] <= 20


# ---------------------------------------------------------------------------
# pattern
# ---------------------------------------------------------------------------


def test_pattern_field_zero_pad() -> None:
    fs = FactSpace(
        fields=[
            FactField(name="seq", kind="int", spec={"min": 7, "max": 7}),
            FactField(
                name="code",
                kind="pattern",
                spec={"template": "{seq:3}"},
            ),
        ]
    )
    result = sample_instance(fs, rng=_make_rng(0))
    assert result["code"] == "007"


def test_pattern_resolves_after_scalars() -> None:
    fs = FactSpace(
        fields=[
            FactField(name="year", kind="int", spec={"min": 2024, "max": 2024}),
            FactField(name="num", kind="int", spec={"min": 1, "max": 1}),
            FactField(
                name="label",
                kind="pattern",
                spec={"template": "{year}-{num:3}"},
            ),
        ]
    )
    result = sample_instance(fs, rng=_make_rng(0))
    assert result["label"] == "2024-001"


# ---------------------------------------------------------------------------
# max_instances guard
# ---------------------------------------------------------------------------


def test_max_instances_guard() -> None:
    fs = FactSpace(
        fields=[FactField(name="x", kind="int", spec={"min": 0, "max": 10})],
        max_instances=3,
    )
    with pytest.raises(FactGenerationError):
        sample_instance(fs, rng=_make_rng(0), draw_index=3)


# ---------------------------------------------------------------------------
# date
# ---------------------------------------------------------------------------


def test_date_field_in_range() -> None:
    import datetime

    fs = FactSpace(
        fields=[
            FactField(
                name="d",
                kind="date",
                spec={"start": "2024-01-01", "end": "2024-12-31"},
            )
        ]
    )
    for seed in range(10):
        result = sample_instance(fs, rng=_make_rng(seed))
        d = datetime.date.fromisoformat(str(result["d"]))
        assert datetime.date(2024, 1, 1) <= d <= datetime.date(2024, 12, 31)


def test_date_field_deterministic() -> None:
    fs = FactSpace(
        fields=[
            FactField(
                name="d",
                kind="date",
                spec={"start": "2024-01-01", "end": "2024-12-31"},
            )
        ]
    )
    result_a = sample_instance(fs, rng=_make_rng(42))
    result_b = sample_instance(fs, rng=_make_rng(42))
    assert result_a["d"] == result_b["d"]


# ---------------------------------------------------------------------------
# name
# ---------------------------------------------------------------------------


def test_name_field_picks_from_pool() -> None:
    pool = ["Alice", "Bob", "Carol"]
    fs = FactSpace(
        fields=[
            FactField(
                name="person",
                kind="name",
                spec={"pool": pool},
            )
        ]
    )
    result = sample_instance(fs, rng=_make_rng(5))
    assert result["person"] in pool


def test_name_empty_pool_raises() -> None:
    fs = FactSpace(
        fields=[
            FactField(
                name="person",
                kind="name",
                spec={"pool": []},
            )
        ]
    )
    with pytest.raises(FactGenerationError):
        sample_instance(fs, rng=_make_rng(0))
