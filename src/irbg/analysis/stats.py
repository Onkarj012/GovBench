from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from irbg.db.operations import (
    DbConfig,
    connect,
    get_pillar_scores_for_model,
)


@dataclass(frozen=True)
class PillarCI:
    pillar: str
    n: int
    mean: float
    ci_low: float
    ci_high: float


@dataclass(frozen=True)
class ModelCI:
    model_alias: str
    mode: str
    pillars: list[PillarCI]
    composite_mean: float
    composite_ci_low: float
    composite_ci_high: float


@dataclass(frozen=True)
class RobustnessDelta:
    pillar: str
    baseline: float
    comparison: float
    delta: float  # baseline − comparison (positive = degraded under pressure)


@dataclass(frozen=True)
class RobustnessReport:
    model_alias: str
    mode_compared: str  # "pressure" or "adversarial"
    pillars: list[RobustnessDelta]
    composite_delta: float


@dataclass(frozen=True)
class PairwiseResult:
    model_a: str
    model_b: str
    pillar: str
    n_a: int
    n_b: int
    u_statistic: float
    p_value: float
    significant: bool  # p < 0.05


@dataclass(frozen=True)
class PairwiseReport:
    mode: str
    comparisons: list[PairwiseResult]


class StatsError(Exception):
    """Raised when statistics cannot be computed."""


_BOOTSTRAP_N = 2000
_CI_ALPHA = 0.05
_SIGNIFICANCE = 0.05


def _bootstrap_ci(
    values: list[float],
    *,
    n_boot: int = _BOOTSTRAP_N,
    alpha: float = _CI_ALPHA,
) -> tuple[float, float]:
    if len(values) < 2:
        v = values[0] if values else 0.0
        return round(v, 2), round(v, 2)
    rng = random.Random(42)
    boot_means = sorted(
        mean(rng.choices(values, k=len(values))) for _ in range(n_boot)
    )
    lo = boot_means[int(alpha / 2 * n_boot)]
    hi = boot_means[int((1 - alpha / 2) * n_boot)]
    return round(lo, 2), round(hi, 2)


def _mann_whitney_u(a: list[float], b: list[float]) -> tuple[float, float]:
    """Exact Mann-Whitney U statistic + two-sided p-value via normal approx.

    Returns (U, p_value). Uses the normal approximation (z-score) which is
    adequate for n ≥ 3; returns p=1.0 when either sample is too small.
    """
    import math

    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return 0.0, 1.0

    # Count U: number of pairs (ai, bj) where ai > bj
    u1 = sum(1 if ai > bj else 0.5 if ai == bj else 0 for ai in a for bj in b)
    u2 = n1 * n2 - u1
    u = min(u1, u2)

    # Normal approximation
    mu = n1 * n2 / 2.0
    sigma = math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12.0)
    if sigma == 0:
        return u, 1.0

    z = (u - mu) / sigma
    # Two-sided p via complementary error function
    p = math.erfc(abs(z) / math.sqrt(2))
    return round(u, 2), round(p, 4)


def compute_pairwise_significance(
    *,
    db_path: Path,
    model_a: str,
    model_b: str,
    mode: str = "baseline",
) -> PairwiseReport:
    """Mann-Whitney U pairwise significance test per pillar."""
    conn = connect(DbConfig(path=db_path))
    try:
        rows_a = get_pillar_scores_for_model(conn, model_id=model_a, mode=mode)
        rows_b = get_pillar_scores_for_model(conn, model_id=model_b, mode=mode)
    finally:
        conn.close()

    if not rows_a:
        raise StatsError(f"No {mode} runs for model '{model_a}'.")
    if not rows_b:
        raise StatsError(f"No {mode} runs for model '{model_b}'.")

    by_pillar_a: dict[str, list[float]] = defaultdict(list)
    for row in rows_a:
        by_pillar_a[str(row["pillar"])].append(float(row["score"]))

    by_pillar_b: dict[str, list[float]] = defaultdict(list)
    for row in rows_b:
        by_pillar_b[str(row["pillar"])].append(float(row["score"]))

    shared = sorted(set(by_pillar_a) & set(by_pillar_b))
    comparisons: list[PairwiseResult] = []
    for pillar in shared:
        a_scores = by_pillar_a[pillar]
        b_scores = by_pillar_b[pillar]
        u, p = _mann_whitney_u(a_scores, b_scores)
        comparisons.append(
            PairwiseResult(
                model_a=model_a,
                model_b=model_b,
                pillar=pillar,
                n_a=len(a_scores),
                n_b=len(b_scores),
                u_statistic=u,
                p_value=p,
                significant=p < _SIGNIFICANCE,
            )
        )

    return PairwiseReport(mode=mode, comparisons=comparisons)


_BOOTSTRAP_N = 2000
_CI_ALPHA = 0.05


def _bootstrap_ci(
    values: list[float],
    *,
    n_boot: int = _BOOTSTRAP_N,
    alpha: float = _CI_ALPHA,
) -> tuple[float, float]:
    if len(values) < 2:
        v = values[0] if values else 0.0
        return round(v, 2), round(v, 2)
    rng = random.Random(42)
    boot_means = sorted(
        mean(rng.choices(values, k=len(values))) for _ in range(n_boot)
    )
    lo = boot_means[int(alpha / 2 * n_boot)]
    hi = boot_means[int((1 - alpha / 2) * n_boot)]
    return round(lo, 2), round(hi, 2)


def compute_model_ci(
    *,
    db_path: Path,
    model_alias: str,
    mode: str = "baseline",
) -> ModelCI:
    conn = connect(DbConfig(path=db_path))
    try:
        rows = get_pillar_scores_for_model(
            conn, model_id=model_alias, mode=mode
        )
    finally:
        conn.close()

    if not rows:
        raise StatsError(
            f"No completed {mode} runs found for model '{model_alias}'."
        )

    by_pillar: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_pillar[str(row["pillar"])].append(float(row["score"]))

    pillar_cis: list[PillarCI] = []
    for pillar, scores in sorted(by_pillar.items()):
        lo, hi = _bootstrap_ci(scores)
        pillar_cis.append(
            PillarCI(
                pillar=pillar,
                n=len(scores),
                mean=round(mean(scores), 2),
                ci_low=lo,
                ci_high=hi,
            )
        )

    all_scores = [s for scores in by_pillar.values() for s in scores]
    comp_lo, comp_hi = _bootstrap_ci(all_scores)

    return ModelCI(
        model_alias=model_alias,
        mode=mode,
        pillars=pillar_cis,
        composite_mean=round(mean(all_scores), 2),
        composite_ci_low=comp_lo,
        composite_ci_high=comp_hi,
    )


def compute_robustness_delta(
    *,
    db_path: Path,
    model_alias: str,
    mode: str = "pressure",
) -> RobustnessReport:
    """Compute baseline − <mode> per pillar (positive = degraded)."""
    conn = connect(DbConfig(path=db_path))
    try:
        base_rows = get_pillar_scores_for_model(
            conn, model_id=model_alias, mode="baseline"
        )
        cmp_rows = get_pillar_scores_for_model(
            conn, model_id=model_alias, mode=mode
        )
    finally:
        conn.close()

    if not base_rows:
        raise StatsError(f"No baseline runs found for model '{model_alias}'.")
    if not cmp_rows:
        raise StatsError(f"No {mode} runs found for model '{model_alias}'.")

    base_by_pillar: dict[str, float] = {}
    for row in base_rows:
        p = str(row["pillar"])
        base_by_pillar[p] = round(
            mean(float(r["score"]) for r in base_rows if str(r["pillar"]) == p),
            2,
        )

    cmp_by_pillar: dict[str, float] = {}
    for row in cmp_rows:
        p = str(row["pillar"])
        cmp_by_pillar[p] = round(
            mean(float(r["score"]) for r in cmp_rows if str(r["pillar"]) == p),
            2,
        )

    deltas: list[RobustnessDelta] = []
    for pillar in sorted(base_by_pillar):
        if pillar not in cmp_by_pillar:
            continue
        b = base_by_pillar[pillar]
        c = cmp_by_pillar[pillar]
        deltas.append(
            RobustnessDelta(
                pillar=pillar,
                baseline=b,
                comparison=c,
                delta=round(b - c, 2),
            )
        )

    composite_delta = round(mean(d.delta for d in deltas), 2) if deltas else 0.0

    return RobustnessReport(
        model_alias=model_alias,
        mode_compared=mode,
        pillars=deltas,
        composite_delta=composite_delta,
    )
