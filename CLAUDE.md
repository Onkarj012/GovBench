# Claude Agent Instructions

This file provides context and instructions for Claude (Anthropic's AI assistant) when working on the IRBG project.

## Quick Reference

- **Project**: IRBG - Institutional Readiness & Bias Benchmark for Governance
- **Language**: Python 3.12+
- **Package Manager**: `uv`
- **Lint/Format**: Ruff (80 char line limit)
- **Tests**: pytest

## Pre-Flight Checklist

Before committing, always run:
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/ -v
```

## Common Tasks

### Adding a New Scoring Module
1. Create `src/irbg/scoring/pX.py` following P1-P6 patterns
2. Add CLI command in `src/irbg/cli.py`
3. Update `aggregate.py` weights if needed
4. Add tests in `tests/test_pX_scoring.py`

### Adding CLI Commands
1. Define function with `@main.command("command-name")`
2. Use click options for arguments
3. Handle errors with `raise click.ClickException(str(exc))`
4. Use Rich console for formatted output

### Database Operations
- Use `DbConfig` and `connect()` from `irbg.db.operations`
- Always wrap in try/finally to close connections
- Use upsert patterns for idempotency

## Code Patterns

### Frozen Dataclass
```python
@dataclass(frozen=True)
class MyResult:
    field1: str
    field2: float
```

### Custom Exception
```python
class MyModuleError(Exception):
    """Raised when something fails."""
```

### Database Upsert
```python
upsert_pillar_score(
    conn,
    run_id=run_id,
    pillar="pX_pillar_name",
    score=result.overall_score,
    breakdown_json=json.dumps(asdict(result)),
    notes="Scored X scenarios",
)
```

## Important Files

- **AGENTS.md** - Additional agent instructions and project context
- **SYSTEM_REPORT.md** - Comprehensive project documentation
- **CONTRIBUTING.md** - Contribution guidelines and conventions
- **config/models.yaml** - LLM model configurations
- **config/demographics.yaml** - Demographic variant groups

## Current Branches

- `main` - Stable, production-ready code
- `feat/add-remaining-pillars` - Completed: P2-P6 scoring (merged)
- `feat/token-efficiency` - Active: Token budget and cost optimization

## Token Efficiency Notes

Current observations:
- DeepSeek-V3: ~501 output tokens/req, ~19s latency
- GPT-OSS 120B: ~1,573 output tokens/req, ~54s latency
- GPT-OSS is 3x more verbose and 2.8x slower

Focus areas for this branch:
1. Add `max_tokens` constraints per pillar
2. Implement conciseness scoring bonus
3. Consider response truncation

## Questions?

Check AGENTS.md for more context or SYSTEM_REPORT.md for full documentation.
