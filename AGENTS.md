# IRBG Agents Documentation

This file contains agent-specific instructions and context for AI assistants working on the IRBG (Institutional Readiness & Bias Benchmark for Governance) project.

## Project Overview

IRBG is a benchmarking framework that evaluates AI language models for demographic bias and governance readiness across 6 pillars:
- P1: Demographic Consistency
- P2: Procedural Integrity
- P3: Corruption Resistance
- P4: Jurisdictional Awareness
- P5: Transparency & Explainability
- P6: Minority Protection

## Key Technical Details

### Architecture
- **Language**: Python 3.12+
- **Package Manager**: `uv`
- **Build System**: Hatchling
- **CLI Framework**: Click
- **Database**: SQLite
- **LLM Provider**: OpenRouter API

### Project Structure
```
irbg/
├── src/irbg/              # Main package
│   ├── cli.py             # CLI commands
│   ├── engine/            # Provider, runner, prompts
│   ├── scenarios/         # Scenario loading & templates
│   ├── scoring/           # P1-P6 scoring modules
│   ├── analysis/          # Aggregate, compare, reporting
│   └── db/                # Database operations
├── scenarios/             # JSON scenario templates
├── config/                # models.yaml, demographics.yaml
└── tests/                 # pytest test suite
```

### Code Style
- **Linter/Formatter**: Ruff (line length: 80)
- **Import Style**: Absolute imports preferred
- **Type Hints**: Use for public functions
- **Dataclasses**: Use `@dataclass(frozen=True)` for data structures
- **Error Handling**: Custom exception per module

### Testing
```bash
# Run all checks
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/ -v
```

### CLI Usage Patterns
```bash
# Run benchmarks
irbg run-template-folder --model <alias> --scenario-folder <path>

# Score runs
irbg score-p1-run --run-id <id>
irbg score-p2-run --run-id <id>
# ... etc for P3-P6

# Aggregate and report
irbg aggregate-run --run-id <id>
irbg report-run --run-id <id>
```

## Current Focus Areas

### Token Efficiency (Active Branch: feat/token-efficiency)
- Add token budget constraints per pillar
- Implement conciseness scoring metric
- Optimize model response lengths
- Reduce API costs while maintaining accuracy

### Known Issues
- GPT-OSS 120B generates 3x more tokens than DeepSeek-V3
- P6 (Minority Protection) has highest token variance
- P5 (Transparency) scoring needs improvement

## Environment Setup

Required environment variables in `.env`:
```bash
OPENROUTER_API_KEY=your_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_APP_NAME=IRBG
OPENROUTER_SITE_URL=https://your-site.com
```

## Contributing Guidelines

1. Follow conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `style:`, `test:`
2. All code must pass ruff checks and tests before committing
3. Update this file if you change architectural patterns
4. See CLAUDE.md for additional context

## Resources

- See [CLAUDE.md](./CLAUDE.md) for additional agent instructions
- See [SYSTEM_REPORT.md](./SYSTEM_REPORT.md) for comprehensive documentation
- See [CONTRIBUTING.md](./CONTRIBUTING.md) for contribution guidelines
