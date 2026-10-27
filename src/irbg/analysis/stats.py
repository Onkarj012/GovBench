from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist, mean
from typing import Any

import numpy as np

from irbg.db.operations import (
    DbConfig,
    connect,
    get_pillar_scores_for_model,
)

_NORMAL = NormalDist()


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


@dataclass(frozen=True)
class ClusteredSEResult:
    """Cluster-robust standard error of the mean."""

    mean: float
    se: float
    naive_se: float
    n_clusters: int
    n: int


@dataclass(frozen=True)
class PairedDifferenceResult:
    """Paired comparison of two models over the same items."""

    mean_diff: float
    se: float
    t_statistic: float
    p_value: float
    cohens_d: float
    n: int
    df: int


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


# ---------------------------------------------------------------------------
# Statistical rigor: cluster-robust SE, paired tests, multiple-comparison
# correction, and power analysis. These are pure functions (no DB access)
# intended for wiring into reporting/CLI in a follow-up.
# Reference: Anthropic, "Adding Error Bars to Evals" (arXiv:2411.00640).
# ---------------------------------------------------------------------------


def _z_quantile(q: float) -> float:
    """Inverse standard-normal CDF (probit) via ``statistics.NormalDist``.

    Returns ``z`` such that ``Φ(z) = q``.
    """
    if q <= 0.0:
        return float("-inf")
    if q >= 1.0:
        return float("inf")
    return _NORMAL.inv_cdf(q)


def _betacf(a: float, b: float, x: float) -> float:
    """Continued-fraction expansion for the incomplete beta function."""
    maxit = 200
    eps = 3.0e-7
    tiny = 1.0e-30
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, maxit + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function ``I_x(a, b)``."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def _t_two_sided_pvalue(t: float, df: float) -> float:
    """Two-sided p-value for a t-statistic with ``df`` degrees of freedom.

    ``p = I_x(df/2, 1/2)`` with ``x = df / (df + t²)``.
    """
    if df <= 0:
        return float("nan")
    if t == 0.0:
        return 1.0
    x = df / (df + t * t)
    return _betai(df / 2.0, 0.5, x)


def clustered_standard_error(
    scores: list[float] | np.ndarray,
    clusters: list[Any] | np.ndarray,
) -> ClusteredSEResult:
    """Cluster-robust standard error of the mean.

    Observations that share a cluster label (e.g. the same scenario
    template id) are treated as correlated; naive iid standard errors
    understate uncertainty when that within-cluster correlation is
    positive. This is the Liang-Zeger cluster-robust sandwich variance
    for an intercept-only model with the ``G/(G-1)`` finite-sample
    correction.

    Args:
        scores: N observation values.
        clusters: N cluster labels (any hashable); ``scores[i]`` belongs
            to ``clusters[i]``.

    Returns:
        :class:`ClusteredSEResult` with the cluster-robust SE, the naive
        iid SE (``sd / sqrt(n)``) for comparison, and counts.
    """
    a = np.asarray(scores, dtype=float)
    c = np.asarray(clusters)
    if a.ndim != 1 or c.ndim != 1:
        raise StatsError("scores and clusters must be 1-D")
    if a.shape[0] != c.shape[0]:
        raise StatsError("scores and clusters must have equal length")
    n = int(a.shape[0])
    if n == 0:
        raise StatsError("cannot compute SE of an empty sample")

    mean = float(a.mean())
    resid = a - mean
    unique = np.unique(c)
    g = int(unique.shape[0])
    cluster_sums = np.array([resid[c == lab].sum() for lab in unique])

    if g > 1:
        var = (g / (g - 1.0)) * float((cluster_sums**2).sum()) / (n**2)
    else:
        var = float(a.var(ddof=1)) / n if n > 1 else 0.0

    se = math.sqrt(var)
    naive_se = float(a.std(ddof=1)) / math.sqrt(n) if n > 1 else 0.0

    return ClusteredSEResult(
        mean=mean,
        se=se,
        naive_se=naive_se,
        n_clusters=g,
        n=n,
    )


def paired_difference_test(
    scores_a: list[float] | np.ndarray,
    scores_b: list[float] | np.ndarray,
) -> PairedDifferenceResult:
    """Paired analysis for two models on the same items.

    Both inputs must be the same length and paired by position (item i
    in ``scores_a`` compared with item i in ``scores_b``). Returns the
    mean difference (``a - b``), its standard error, the paired
    t-statistic, two-sided p-value, and Cohen's d (paired form:
    ``mean_diff / sd of differences``).
    """
    a = np.asarray(scores_a, dtype=float)
    b = np.asarray(scores_b, dtype=float)
    if a.shape[0] != b.shape[0]:
        raise StatsError("scores_a and scores_b must be paired (equal length)")
    n = int(a.shape[0])
    if n < 2:
        raise StatsError("paired test requires at least 2 paired observations")

    diffs = a - b
    mean_diff = float(diffs.mean())
    sd_diff = float(diffs.std(ddof=1))
    se = sd_diff / math.sqrt(n)

    if se == 0.0:
        t_stat = float("inf") if mean_diff != 0.0 else 0.0
        p = 0.0 if mean_diff != 0.0 else 1.0
    else:
        t_stat = mean_diff / se
        p = _t_two_sided_pvalue(t_stat, n - 1)

    cohens_d = mean_diff / sd_diff if sd_diff != 0.0 else float("nan")

    return PairedDifferenceResult(
        mean_diff=mean_diff,
        se=se,
        t_statistic=t_stat,
        p_value=p,
        cohens_d=cohens_d,
        n=n,
        df=n - 1,
    )


def holm_bonferroni(pvalues: list[float]) -> list[float]:
    """Holm step-down adjusted p-values, returned in original order.

    Controls the family-wise error rate. For ``m`` p-values sorted
    ascending, the ``i``-th smallest is multiplied by ``(m - i + 1)``;
    monotonicity is enforced via a running maximum and every value is
    capped at 1.0.
    """
    m = len(pvalues)
    if m == 0:
        return []

    indexed = sorted(enumerate(pvalues), key=lambda kv: kv[1])
    adjusted_sorted = [0.0] * m
    running_max = 0.0
    for rank, (_orig_idx, p) in enumerate(indexed):
        adj = p * (m - rank)
        if adj < running_max:
            adj = running_max
        if adj > 1.0:
            adj = 1.0
        running_max = adj
        adjusted_sorted[rank] = adj

    out = [0.0] * m
    for rank, (orig_idx, _p) in enumerate(indexed):
        out[orig_idx] = adjusted_sorted[rank]
    return out


def power_analysis_mde(
    sd: float,
    n: int,
    alpha: float = 0.05,
    power: float = 0.8,
) -> float:
    """Minimum detectable effect (MDE) for a paired/one-sample design.

    The smallest true mean difference detectable at significance level
    ``alpha`` and ``power``, given paired differences with standard
    deviation ``sd`` over ``n`` items. Uses the normal (z) approximation
    standard in eval power analysis.
    """
    if n <= 0:
        raise StatsError("n must be positive")
    if sd < 0:
        raise StatsError("sd must be non-negative")
    z_alpha = _z_quantile(1.0 - alpha / 2.0)
    z_power = _z_quantile(power)
    return (z_alpha + z_power) * sd / math.sqrt(n)


def required_n(
    sd: float,
    mde: float,
    alpha: float = 0.05,
    power: float = 0.8,
) -> float:
    """Inverse of :func:`power_analysis_mde`: items needed to detect ``mde``.

    Returns the continuous sample size; callers should round up (ceil)
    for a concrete plan. Round-trips with :func:`power_analysis_mde`:
    ``required_n(sd, power_analysis_mde(sd, n)) == n``.
    """
    if mde <= 0:
        raise StatsError("mde must be positive")
    if sd < 0:
        raise StatsError("sd must be non-negative")
    z_alpha = _z_quantile(1.0 - alpha / 2.0)
    z_power = _z_quantile(power)
    return ((z_alpha + z_power) * sd / mde) ** 2
