# GovBench — Agent Instructions

Context and instructions for AI assistants working on this project.

## What is GovBench

GovBench (Governance Benchmark) evaluates AI language models for institutional readiness and demographic bias across 6 governance pillars. It runs structured scenario prompts through models via OpenRouter, scores responses with a GPT-4o judge, and produces per-run reports.

**Pillars:**
- P1: Demographic Consistency — same case, different demographic identifiers
- P2: Procedural Integrity — scenarios with embedded procedural violations
- P3: Corruption Resistance — adversarial multi-turn pressure to change recommendations
- P4: Jurisdictional Awareness — cross-border / multi-jurisdiction cases
- P5: Transparency & Explainability — cases with missing info requiring explicit uncertainty
- P6: Minority Protection — cases involving protected characteristics

**Run modes:** `baseline` · `pressure` (urgency framing) · `adversarial` (P3 only, multi-turn)

**Jurisdictions:** US · EU · India

## Project Layout

```
govbench/
├── src/irbg/              # Python package (entrypoint: irbg CLI)
│   ├── cli.py             # All Click commands
│   ├── engine/            # provider.py, runner.py, prompt_builder.py, variant_generator.py
│   ├── scenarios/         # template_loader.py, loader.py, models.py, discovery.py
│   ├── scoring/           # p1.py – p6.py, judge.py
│   ├── analysis/          # aggregate.py, compare.py, reporting.py, visualize.py
│   └── db/                # schema.py, operations.py
├── scenarios/             # JSON scenario templates (p1_demographic/ … p6_minority/)
├── config/                # models.yaml, demographics.yaml
├── reports/               # Per-model run outputs (<model-alias>/<mode>_<id>_report.*)
├── outputs/graphify/      # Graphify dependency graph output
├── scripts/               # run_full_benchmark.py
├── frontend/              # Next.js (App Router) site — GovBench leaderboard & docs
├── tests/                 # pytest suite
├── pyproject.toml         # package: govbench, entrypoint: irbg
└── main.py                # thin wrapper
```

## Stack

| Layer | Choice |
|---|---|
| Language | Python 3.12+ |
| Package manager | `uv` |
| Build | Hatchling |
| CLI | Click |
| Database | SQLite (`irbg.sqlite`) |
| LLM provider | OpenRouter API |
| Judge model | `gpt-4o` (configured in `config/models.yaml`) |
| Frontend | Next.js 16 + Tailwind CSS v4 + TypeScript |

## Code Conventions

- **Linter/formatter:** Ruff, line length 80, target Python 3.12
- **Imports:** absolute preferred
- **Types:** type hints on all public functions
- **Data structures:** `@dataclass(frozen=True)`
- **Errors:** one custom exception class per module

## Environment

```bash
OPENROUTER_API_KEY=your_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_APP_NAME=GovBench
OPENROUTER_SITE_URL=https://your-site.com
```

## Common Commands

```bash
# Quality checks (run before every commit)
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/ -v

# Run a benchmark
irbg run-template-folder --model gemini-3.1-flash-lite \
  --scenario-folder scenarios/p1_demographic

# Score, aggregate, report
irbg score-p1-run --run-id <id>
irbg aggregate-run --run-id <id>
irbg report-run --run-id <id>

# Frontend
cd frontend && npm run dev
```

## Active Branch: feat/frontend

Current work: Next.js frontend at `frontend/` with leaderboard, per-model detail, blog, docs, and data explorer pages. Design system follows `frontend/design.md` (extracted from DeepSWE reference).

## Scoring Methodology

- **P1 (bias)** is fairness-first: the headline is `decision_score` (share
  of demographic variants receiving the majority decision) with a reported
  `parity_gap` (the disparity). Length/sentiment are demoted to a 20%
  secondary "tone" signal. Decision extraction uses regex with a judge-based
  classifier fallback when inconclusive (`scoring/judge.classify_decision`).
- **P2–P6** use a **multi-judge ensemble** (`judge_models` in
  `config/models.yaml`). Scores are averaged; spread ≥ 25 raises a
  `judge_disagreement` flag. Same-family judges are excluded per
  model-under-test to control self-preference bias.
- **Judge results are cached durably** in the `judge_results` table
  (content-addressed), so re-scoring is free and auditable.
- **Composite/grade** loads weights from `pillar_weights` and only assigns a
  letter grade when **all 6 pillars** are present; partial runs report a
  composite but grade `N/A` (`complete = false`).
- **Prompt harness** is decoupled from scoring: the conciseness suffix and
  per-pillar token budgets are opt-in and **exclude P5/P6**, whose rubrics
  reward elaboration.
- **Judge calibration:** `irbg calibrate-judge` scores a gold set
  (`config/judge_calibration.json`) and reports Cohen's κ vs gold + mean
  absolute error.

## Known Issues

- Corpus is small (3 scenarios/pillar) — Phase 4 will scale it; current
  results are directional, not statistically powered.
- GLM 4.7 Flash and Kimi K2.6 score near-zero on most pillars — likely prompt
  format mismatch.
- No repeated sampling / confidence intervals yet (Phase 3).
