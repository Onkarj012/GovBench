# GovBench

**Governance Benchmark** — evaluating AI language models for institutional readiness and demographic bias across 6 governance pillars.

## What it does

GovBench runs structured legal and administrative scenario prompts through AI models, scores responses with a GPT-4o judge, and produces per-run reports. It tests for:

| Pillar | What it measures |
|---|---|
| P1: Demographic Consistency | Same case, different demographic identifiers — detects bias |
| P2: Procedural Integrity | Scenarios with embedded violations — tests rule-following |
| P3: Corruption Resistance | Adversarial multi-turn pressure — tests recommendation stability |
| P4: Jurisdictional Awareness | Cross-border cases — tests legal framework selection |
| P5: Transparency & Explainability | Missing information — tests uncertainty acknowledgment |
| P6: Minority Protection | Protected characteristics — tests application of protective law |

**Jurisdictions:** US · EU · India  
**Run modes:** `baseline` · `pressure` · `adversarial`  
**Models evaluated:** Claude Sonnet 4.6, DeepSeek V3/V4 Flash, Gemini 3.1 Flash Lite, GPT OSS 120B, Kimi K2.6, GLM 4.7 Flash

## Quickstart

```bash
git clone https://github.com/onkarj012/govbench
cd govbench
uv sync
cp .env.example .env  # add OPENROUTER_API_KEY

# Run a benchmark
irbg run-template-folder \
  --model gemini-3.1-flash-lite \
  --scenario-folder scenarios/p1_demographic

# Score and report
irbg score-p1-run --run-id <id>
irbg aggregate-run --run-id <id>
irbg report-run --run-id <id>
```

## Project layout

```
├── src/irbg/       # Python package (CLI entrypoint: irbg)
├── scenarios/      # JSON scenario templates per pillar
├── config/         # models.yaml, demographics.yaml
├── reports/        # Per-model run outputs
├── scripts/        # run_full_benchmark.py
├── frontend/       # Next.js leaderboard site
└── tests/          # pytest suite
```

## Frontend

```bash
cd frontend && npm run dev
```

Leaderboard at `localhost:3000` with `/blog`, `/docs`, `/data`, and per-model detail pages.

## Stack

Python 3.12 · uv · Click · SQLite · OpenRouter · Next.js 16 · Tailwind CSS v4

## License

[MIT](LICENSE)
