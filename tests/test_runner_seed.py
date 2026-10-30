from __future__ import annotations

import random

from irbg.engine.fact_generator import (
    FactField,
    FactSpace,
    sample_instance,
    seed_for,
)


def _make_fs() -> FactSpace:
    return FactSpace(
        fields=[
            FactField(
                name="color",
                kind="choice",
                spec={"values": ["red", "blue"]},
            ),
            FactField(name="n", kind="int", spec={"min": 1, "max": 100}),
        ]
    )


def test_same_seed_same_instance() -> None:
    """Sampling with the same seed twice should produce identical results."""
    fs = _make_fs()
    rng1 = random.Random(seed_for("template_x", 42))
    rng2 = random.Random(seed_for("template_x", 42))
    result1 = sample_instance(fs, rng=rng1)
    result2 = sample_instance(fs, rng=rng2)
    assert result1 == result2


def test_different_template_seeds_differ() -> None:
    """Different template IDs with same run seed produce different seeds."""
    s1 = seed_for("t1", 42)
    s2 = seed_for("t2", 42)
    assert s1 != s2


def test_seed_for_deterministic() -> None:
    """seed_for must return the same integer on repeated calls."""
    assert seed_for("my_template", 99) == seed_for("my_template", 99)
    assert seed_for("other", 0) == seed_for("other", 0)
