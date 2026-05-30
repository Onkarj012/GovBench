from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from irbg.paths import CONFIG_DIR
from irbg.scoring.judge import judge_response


class CalibrationError(Exception):
    """Raised when judge calibration cannot be performed."""


@dataclass(frozen=True)
class CalibrationItem:
    id: str
    pillar: str
    gold_score: float
    judge_score: float
    gold_bin: str
    judge_bin: str


@dataclass(frozen=True)
class CalibrationReport:
    n: int
    cohens_kappa: float
    mean_abs_error: float
    items: list[CalibrationItem]


def _bin(score: float) -> str:
    if score < 50:
        return "low"
    if score < 80:
        return "mid"
    return "high"


def cohens_kappa(rater_a: list[str], rater_b: list[str]) -> float:
    """Cohen's kappa for two raters over categorical labels."""
    n = len(rater_a)
    if n == 0 or n != len(rater_b):
        return 0.0

    po = sum(1 for a, b in zip(rater_a, rater_b, strict=True) if a == b) / n

    count_a = Counter(rater_a)
    count_b = Counter(rater_b)
    pe = sum(
        (count_a[label] / n) * (count_b[label] / n)
        for label in set(rater_a) | set(rater_b)
    )

    if pe >= 1.0:
        return 1.0
    return round((po - pe) / (1.0 - pe), 4)


def calibrate_judges(
    *,
    calibration_path: Path | None = None,
    db_path: Path | None = None,
) -> CalibrationReport:
    """Score a gold-labelled set and report judge/gold agreement (kappa)."""
    path = calibration_path or (CONFIG_DIR / "judge_calibration.json")
    if not path.exists():
        raise CalibrationError(f"Calibration set not found: {path}")

    items = json.loads(path.read_text())
    if not isinstance(items, list) or not items:
        raise CalibrationError("Calibration set is empty or malformed.")

    results: list[CalibrationItem] = []
    judge_bins: list[str] = []
    gold_bins: list[str] = []
    abs_errors: list[float] = []

    for item in items:
        verdict = judge_response(
            pillar=str(item["pillar"]),
            scenario_context=str(item["scenario_context"]),
            response_text=str(item["response_text"]),
            db_path=db_path,
        )
        gold = float(item["gold_score"])
        gold_bin = _bin(gold)
        judge_bin = _bin(verdict.score)

        gold_bins.append(gold_bin)
        judge_bins.append(judge_bin)
        abs_errors.append(abs(verdict.score - gold))

        results.append(
            CalibrationItem(
                id=str(item["id"]),
                pillar=str(item["pillar"]),
                gold_score=gold,
                judge_score=verdict.score,
                gold_bin=gold_bin,
                judge_bin=judge_bin,
            )
        )

    return CalibrationReport(
        n=len(results),
        cohens_kappa=cohens_kappa(judge_bins, gold_bins),
        mean_abs_error=round(mean(abs_errors), 2) if abs_errors else 0.0,
        items=results,
    )
