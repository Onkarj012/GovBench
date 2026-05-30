from __future__ import annotations

from irbg.scoring.calibration import _bin, cohens_kappa


def test_bin_thresholds() -> None:
    assert _bin(10) == "low"
    assert _bin(49.9) == "low"
    assert _bin(50) == "mid"
    assert _bin(79.9) == "mid"
    assert _bin(80) == "high"
    assert _bin(100) == "high"


def test_cohens_kappa_perfect_agreement() -> None:
    a = ["high", "low", "mid", "high"]
    assert cohens_kappa(a, list(a)) == 1.0


def test_cohens_kappa_no_agreement() -> None:
    a = ["high", "high", "low", "low"]
    b = ["low", "low", "high", "high"]
    assert cohens_kappa(a, b) < 0.0


def test_cohens_kappa_empty() -> None:
    assert cohens_kappa([], []) == 0.0
