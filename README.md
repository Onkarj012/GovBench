# GovBench v2

GovBench tests how language models respond to pressure in Indian public office.
It gives a model a case as a magistrate, District Collector, or procurement
officer, then applies pressure over several turns. Each role runs in two stances,
as the decision-maker and as an advisor.

Results report hold, bend, break, refusal, escalation, and updates after new facts
by role and pressure. There is no composite score or letter grade. V2 replaces
the earlier six-pillar benchmark. V1 code remains under `scenarios/v1` and the
older engine for reference.

## Preliminary results

Read the [30 October 2026 write-up](reports/v2-preview-2026-10-30.md), with counts,
descriptive confidence intervals, role-by-pressure data, and limitations.

All 1,280 completed episodes have been processed, with 76 unresolved judge
disagreements. Other model runs are incomplete. These are exploratory results
from draft scenarios with incomplete historical provenance, not a model ranking.

**The episodes and answer keys will undergo lawyer review in the near future.
We will version any resulting corrections and update the scores.** Procurement
hard-case keys and citations still need review. No lawyer review is claimed.

## Run a new cohort

Use Python 3.12+ and `uv`. Codex and Claude Code backends require their respective
CLIs and working model access. OpenRouter models require `OPENROUTER_API_KEY` in
`.env`. Models, judge identities, seeds, and role prompts are in `config/v2.yaml`.

```bash
uv sync
uv run python scripts/check_v2_scenarios.py scenarios/v2

# Use a new run name after changing scenarios, model settings, or role prompts.
uv run irbg v2 run --run-name my-v2-cohort --models claude-haiku-5.5 --splits public --max-usd 5
uv run irbg v2 classify --run-name my-v2-cohort
uv run irbg v2 status --run-name my-v2-cohort

# Default export includes only publishable scenarios. Drafts require this flag.
uv run irbg v2 export --run-name my-v2-cohort --include-draft --out outputs/my-v2-cohort.json
```

The database is `outputs/v2/govbench-v2.sqlite`. Completed episodes can resume
only with matching input identities. Historical runs without complete identity
records require a fresh run. The OpenRouter budget is a stop threshold based on
recorded or configured pricing. Paid calls share a lock across workers and
processes; the next call may exceed the remaining amount before its cost is
known. CLI backend subscription costs are not measured by this threshold.

Public scenarios live in `scenarios/v2`. Private holdout scenarios are local and
gitignored. This checkout has 81 public drafts, comprising 54 standard and 27
hard cases. Hard cases add separate controls that supply a new, legally relevant
fact. The control measures whether a model can update as well as resist pressure.

## Inspect the site

```bash
cd frontend
npm ci
npm run dev
```

Open `http://localhost:3000`. The site reads frozen public JSON, not the local
SQLite database. The Sol cohort has a separate export so refreshing the main
run does not erase it. Historical scores describe the saved transcripts, not
later revisions to the scenario files.

## Method and checks

Read [VISION.md](VISION.md), [SCHEMA.md](SCHEMA.md), and the
[scenario guide](scenarios/v2/README.md). The blind judge panel uses Sol 6.1 and
Opus 5.5. Relevant flag disagreements remain unresolved and do not enter settled
pressure rates. Wrong initial decisions are reported separately from breaks.

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/ -q
npm --prefix frontend run build
```

Python, Click, SQLite, OpenRouter, Codex CLI, Claude Code, Next.js, and Tailwind.

[MIT license](LICENSE)
