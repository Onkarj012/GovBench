"""Validate v2 scenario folders: schema, rendering, and corpus coverage."""

from __future__ import annotations

import random
import sys
from collections import Counter
from pathlib import Path

from irbg.engine.fact_generator import parse_fact_space, sample_instance
from irbg.scenarios.v2 import ScenarioV2, ScenarioV2Error, load_v2_folder


def _render_all(s: ScenarioV2, draws: int = 5) -> list[str]:
    """Render the case and every turn for several seeds; return problems."""
    problems: list[str] = []
    space = parse_fact_space(s.fact_space) if s.fact_space else None
    for seed in range(draws):
        values = (
            sample_instance(space, rng=random.Random(seed)) if space else {}
        )
        texts = [s.case_template] + [t.text for t in s.pressure_turns]
        if s.control is not None:
            texts.append(s.control.text)
        for text in texts:
            try:
                out = text.format(**values)
            except (KeyError, IndexError, ValueError) as exc:
                problems.append(f"{s.id}: render failed: {exc!r}")
                continue
            if "{" in out or "}" in out:
                problems.append(f"{s.id}: unrendered braces after format")
    return problems


def main(folders: list[str]) -> int:
    """Check each folder and print a coverage table."""
    problems: list[str] = []
    cells: Counter[tuple[str, str, str]] = Counter()
    for folder in folders:
        try:
            scenarios = load_v2_folder(Path(folder))
        except ScenarioV2Error as exc:
            print(f"INVALID: {exc}")
            return 1
        for s in scenarios:
            problems.extend(_render_all(s))
            cells[(s.split, s.role, s.pressure)] += 1
    for key in sorted(cells):
        print(f"{key[0]:8} {key[1]:12} {key[2]:16} {cells[key]}")
    print(f"total: {sum(cells.values())}")
    for p in problems:
        print(f"PROBLEM: {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["scenarios/v2"]))
