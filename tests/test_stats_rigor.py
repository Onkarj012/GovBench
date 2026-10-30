from __future__ import annotations

import math

import numpy as np
import pytest

from irbg.analysis.stats import (
    ClusteredSEResult,
    PairedDifferenceResult,
    StatsError,
    clustered_standard_error,
    holm_bonferroni,
    paired_difference_test,
    power_analysis_mde,
    required_n,
)

# ---------------------------------------------------------------------------
# Clustered standard error
# ---------------------------------------------------------------------------


def test_clustered_se_positive_within_cluster_correlation() -> None:
    """Cluster-robust SE must be >= naive iid SE when clusters are
    internally homogeneous (positive within-cluster correlation)."""
    scores = [10.0, 10.0, 10.0, 0.0, 0.0, 0.0]
    clusters = ["a", "a", "a", "b", "b", "b"]

    result = clustered_standard_error(scores, clusters)

    assert isinstance(result, ClusteredSEResult)
    assert result.n == 6
    assert result.n_clusters == 2
    assert result.mean == pytest.approx(5.0)
    # Exact cluster-robust SE: (G/(G-1)) * sqrt(15^2 + 15^2) / 6 = 5.0
    assert result.se == pytest.approx(5.0)
    # Naive SE = sd(ddof=1)/sqrt(6) = sqrt(30)/sqrt(6) = sqrt(5).
    assert result.naive_se == pytest.approx(math.sqrt(5.0))
    assert result.se > result.naive_se


def test_clustered_se_mismatched_length_raises() -> None:
    with pytest.raises(StatsError):
        clustered_standard_error([1.0, 2.0, 3.0], ["a", "b"])


def test_clustered_se_accepts_numpy() -> None:
    result = clustered_standard_error(
        np.array([1.0, 2.0, 3.0, 4.0]),
        np.array(["x", "x", "y", "y"]),
    )
    assert result.n == 4
    assert result.n_clusters == 2


# ---------------------------------------------------------------------------
# Holm-Bonferroni
# ---------------------------------------------------------------------------


def test_holm_known_worked_example() -> None:
    """Hand-worked Holm step-down with monotonicity enforcement.

    p = [0.01, 0.04, 0.03], m = 3.
      sorted ascending: (0.01 @0), (0.03 @2), (0.04 @1)
      multipliers:      3,        2,        1
      raw adjusted:     0.03,     0.06,     0.04
      running max:      0.03,     0.06,     0.06   (last forced up)
      back to order:    [0.03, 0.06, 0.06]
    """
    adjusted = holm_bonferroni([0.01, 0.04, 0.03])
    assert adjusted == [0.03, 0.06, 0.06]


def test_holm_preserves_original_order() -> None:
    adjusted = holm_bonferroni([0.04, 0.01, 0.03])
    # 0.01 is smallest (x3 = 0.03), 0.03 next (x2 = 0.06), 0.04 (x1 -> 0.06).
    assert adjusted[0] == pytest.approx(0.06)  # original idx 0, p=0.04
    assert adjusted[1] == pytest.approx(0.03)  # original idx 1, p=0.01
    assert adjusted[2] == pytest.approx(0.06)  # original idx 2, p=0.03


def test_holm_caps_at_one() -> None:
    adjusted = holm_bonferroni([0.5, 0.5])
    assert adjusted == [1.0, 1.0]


def test_holm_single_and_empty() -> None:
    assert holm_bonferroni([0.03]) == [0.03]
    assert holm_bonferroni([]) == []


def test_holm_monotonicity_small_pvalues() -> None:
    # All tiny, distinct p-values: multipliers shrink across ranks but
    # monotonicity forces the largest up to the running max.
    # p=[0.001,0.002,0.003], m=3:
    #   sorted: (0.001 x3=0.003), (0.002 x2=0.004), (0.003 x1=0.003 -> 0.004)
    adjusted = holm_bonferroni([0.001, 0.002, 0.003])
    assert adjusted[0] == pytest.approx(0.003)
    assert adjusted[1] == pytest.approx(0.004)
    assert adjusted[2] == pytest.approx(0.004)  # forced to running max
    assert all(p <= 1.0 for p in adjusted)


# ---------------------------------------------------------------------------
# Paired difference test
# ---------------------------------------------------------------------------


def test_paired_difference_hand_computed() -> None:
    """Hand-computable fixture: a=[1..5], b=[2,4,6,8,10].

    diffs = [-1,-2,-3,-4,-5], mean_diff = -3.0,
    sample sd of diffs = sqrt(2.5) ≈ 1.5811,
    se = sqrt(2.5)/sqrt(5) = sqrt(0.5) ≈ 0.7071,
    t = -3 / sqrt(0.5) = -3*sqrt(2) ≈ -4.2426, df = 4,
    Cohen's d = -3 / sqrt(2.5) ≈ -1.8974.
    """
    a = [1.0, 2.0, 3.0, 4.0, 5.0]
    b = [2.0, 4.0, 6.0, 8.0, 10.0]

    result = paired_difference_test(a, b)

    assert isinstance(result, PairedDifferenceResult)
    assert result.n == 5
    assert result.df == 4
    assert result.mean_diff == pytest.approx(-3.0)
    assert result.se == pytest.approx(math.sqrt(0.5))
    assert result.t_statistic == pytest.approx(-3.0 * math.sqrt(2.0))
    assert result.cohens_d == pytest.approx(-3.0 / math.sqrt(2.5))
    # Two-sided p for t=-4.2426, df=4 is ~0.0132.
    assert result.p_value == pytest.approx(0.0132, abs=0.01)
    assert 0.0 < result.p_value < 0.05


def test_paired_difference_zero_diff() -> None:
    """Identical series -> mean_diff 0, t 0, p 1; Cohen's d undefined (nan)."""
    result = paired_difference_test([3.0, 4.0, 5.0], [3.0, 4.0, 5.0])
    assert result.mean_diff == 0.0
    assert result.t_statistic == 0.0
    assert result.p_value == 1.0
    assert math.isnan(result.cohens_d)


def test_paired_difference_constant_diff() -> None:
    """All diffs equal -> zero sd, infinite t, p 0."""
    result = paired_difference_test([1.0, 2.0, 3.0], [4.0, 5.0, 6.0])
    assert result.mean_diff == pytest.approx(-3.0)
    assert math.isinf(result.t_statistic)
    assert result.p_value == 0.0


def test_paired_difference_length_mismatch_raises() -> None:
    with pytest.raises(StatsError):
        paired_difference_test([1.0, 2.0], [1.0, 2.0, 3.0])


def test_paired_difference_vs_scipy() -> None:
    """Cross-check t and p against scipy.stats.ttest_rel when usable."""
    try:
        from scipy import stats as scipy_stats
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"scipy not usable in this environment: {exc!r}")

    a = [1.2, 2.3, 3.1, 4.8, 5.6, 6.9, 7.2, 8.1]
    b = [1.8, 2.1, 4.0, 4.1, 6.2, 6.0, 8.5, 7.6]

    try:
        ref = scipy_stats.ttest_rel(a, b)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"scipy.stats not callable here: {exc!r}")

    result = paired_difference_test(a, b)

    assert result.t_statistic == pytest.approx(ref.statistic, rel=1e-6)
    assert result.p_value == pytest.approx(ref.pvalue, rel=1e-6)
    # Cohen's d (paired) = mean_diff / sd(ddof=1) of differences.
    diffs = np.array(a) - np.array(b)
    expected_d = diffs.mean() / diffs.std(ddof=1)
    assert result.cohens_d == pytest.approx(float(expected_d), rel=1e-6)


# ---------------------------------------------------------------------------
# Power analysis
# ---------------------------------------------------------------------------


def test_power_mde_known_value() -> None:
    """sd=1, n=64, alpha=0.05, power=0.8 -> mde = (1.96+0.8416)/8 ≈ 0.3502."""
    mde = power_analysis_mde(sd=1.0, n=64, alpha=0.05, power=0.8)
    assert mde == pytest.approx(0.3502, abs=0.001)


def test_power_round_trip() -> None:
    """required_n(sd, power_analysis_mde(sd, n)) == n for several n."""
    sd = 1.5
    for n in (8, 16, 25, 64, 100, 250):
        mde = power_analysis_mde(sd=sd, n=n)
        n_back = required_n(sd=sd, mde=mde)
        assert n_back == pytest.approx(n, rel=1e-9)


def test_power_round_trip_custom_alpha_power() -> None:
    sd = 2.0
    mde = power_analysis_mde(sd=sd, n=50, alpha=0.01, power=0.9)
    assert required_n(sd=sd, mde=mde, alpha=0.01, power=0.9) == pytest.approx(
        50, rel=1e-9
    )


def test_required_n_decreases_with_larger_mde() -> None:
    n_small = required_n(sd=1.0, mde=0.1)
    n_large = required_n(sd=1.0, mde=1.0)
    assert n_small > n_large


def test_power_invalid_inputs_raise() -> None:
    with pytest.raises(StatsError):
        power_analysis_mde(sd=1.0, n=0)
    with pytest.raises(StatsError):
        required_n(sd=1.0, mde=0.0)
