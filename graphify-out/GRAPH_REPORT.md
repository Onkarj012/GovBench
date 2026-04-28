# Graph Report - .  (2026-04-22)

## Corpus Check
- Corpus is ~14,603 words - fits in a single context window. You may not need a graph.

## Summary
- 227 nodes · 491 edges · 25 communities detected
- Extraction: 56% EXTRACTED · 44% INFERRED · 0% AMBIGUOUS · INFERRED: 214 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Database Layer|Database Layer]]
- [[_COMMUNITY_Template Engine|Template Engine]]
- [[_COMMUNITY_Reporting & Visualization|Reporting & Visualization]]
- [[_COMMUNITY_Execution Runner|Execution Runner]]
- [[_COMMUNITY_LLM Provider|LLM Provider]]
- [[_COMMUNITY_CLI & Commands|CLI & Commands]]
- [[_COMMUNITY_P1 Consistency Scoring|P1 Consistency Scoring]]
- [[_COMMUNITY_Demographics Config|Demographics Config]]
- [[_COMMUNITY_Model Configuration|Model Configuration]]
- [[_COMMUNITY_Benchmark Reports|Benchmark Reports]]
- [[_COMMUNITY_Scenario Loader|Scenario Loader]]
- [[_COMMUNITY_Package Initializers|Package Initializers]]
- [[_COMMUNITY_Graph Reporting|Graph Reporting]]
- [[_COMMUNITY_Test Fixtures|Test Fixtures]]
- [[_COMMUNITY_P2 Scoring|P2 Scoring]]
- [[_COMMUNITY_Contributing Guide|Contributing Guide]]
- [[_COMMUNITY_Entry Point|Entry Point]]
- [[_COMMUNITY_Provider Interface|Provider Interface]]
- [[_COMMUNITY_Template Interface|Template Interface]]
- [[_COMMUNITY_Path Definitions|Path Definitions]]
- [[_COMMUNITY_Package Root|Package Root]]
- [[_COMMUNITY_DB Init|DB Init]]
- [[_COMMUNITY_IRBG Overview|IRBG Overview]]
- [[_COMMUNITY_Vaani Reference|Vaani Reference]]
- [[_COMMUNITY_Graph Report|Graph Report]]

## God Nodes (most connected - your core abstractions)
1. `connect()` - 18 edges
2. `run_single_template_variant()` - 18 edges
3. `run_template_folder()` - 18 edges
4. `DbConfig` - 17 edges
5. `run_all_template_variants()` - 17 edges
6. `_ensure_database()` - 16 edges
7. `build_run_report()` - 16 edges
8. `run_single_scenario()` - 16 edges
9. `aggregate_run_score()` - 14 edges
10. `OpenRouterClient` - 14 edges

## Surprising Connections (you probably didn't know these)
- `Baseline Mode` --semantically_similar_to--> `Baseline Latency Metric`  [INFERRED] [semantically similar]
  reports/2bdd743782c34e93bb4c39d0ea132fb9_report.md → reports/2bdd743782c34e93bb4c39d0ea132fb9_latency.png
- `Pressure Mode` --semantically_similar_to--> `Pressure Latency Metric`  [INFERRED] [semantically similar]
  reports/38c06205c9ef44bb8f7e03c75cd0b1b4_report.md → reports/38c06205c9ef44bb8f7e03c75cd0b1b4_latency.png
- `test_get_model_config()` --calls--> `get_model_config()`  [INFERRED]
  /Users/onkarj012/Projects/benchmarks/irbg/tests/test_config.py → /Users/onkarj012/Projects/benchmarks/irbg/src/irbg/config.py
- `list_runs()` --calls--> `list_benchmark_runs()`  [INFERRED]
  /Users/onkarj012/Projects/benchmarks/irbg/src/irbg/cli.py → /Users/onkarj012/Projects/benchmarks/irbg/src/irbg/db/operations.py
- `test_build_run_report()` --calls--> `upsert_scenario_record()`  [INFERRED]
  /Users/onkarj012/Projects/benchmarks/irbg/tests/test_reporting.py → /Users/onkarj012/Projects/benchmarks/irbg/src/irbg/db/operations.py

## Hyperedges (group relationships)
- **Benchmark Mode Comparison** — report_mode_baseline, report_mode_pressure, report_deepseek_v3, p1_demographic_consistency [EXTRACTED 1.00]
- **IRBG Core Architecture** — graph_report_dbconfig, graph_report_openrouterclient, graph_report_connect, graph_report_run_single_template_variant, graph_report_aggregated_run_score [INFERRED 0.75]
- **Reporting and Visualization Pipeline** — graph_report_build_run_report, report_latency_baseline, report_latency_pressure, report_pillar_baseline, report_pillar_pressure [EXTRACTED 1.00]

## Communities

### Community 0 - "Database Layer"
Cohesion: 0.15
Nodes (29): aggregate_run_score(), AggregatedRunScore, _grade_from_score(), connect(), create_benchmark_run(), DbConfig, get_all_pillar_scores(), get_irbg_score() (+21 more)

### Community 1 - "Template Engine"
Cohesion: 0.1
Nodes (25): render_template(), PromptBuildError, Raised when a prompt cannot be rendered from a template., render_prompt(), _resolve_mode_overlay(), load_scenario_template(), _optional_str(), _parse_adversarial_turns() (+17 more)

### Community 2 - "Reporting & Visualization"
Cohesion: 0.14
Nodes (15): AggregateScoreError, Raised when a run cannot be aggregated., report_run_cmd(), load_template_files(), Raised when scenario files cannot be discovered., ScenarioDiscoveryError, Exception, Raised when a run report cannot be generated. (+7 more)

### Community 3 - "Execution Runner"
Cohesion: 0.32
Nodes (16): get_model_config(), mark_benchmark_run_completed(), mark_benchmark_run_failed(), upsert_scenario(), upsert_scenario_record(), _build_client_from_env(), _build_rendered_prompts_for_template(), _execute_adversarial_sequence() (+8 more)

### Community 4 - "LLM Provider"
Cohesion: 0.21
Nodes (6): ping_openrouter(), OpenRouterClient, test_openrouter_client_chat_messages_success(), test_openrouter_client_chat_success(), ChatMessage, ProviderResponse

### Community 5 - "CLI & Commands"
Cohesion: 0.22
Nodes (13): aggregate_run_cmd(), compare_runs_cmd(), _ensure_database(), init_db(), list_runs(), run_once(), run_template_folder_cmd(), run_template_group() (+5 more)

### Community 6 - "P1 Consistency Scoring"
Cohesion: 0.28
Nodes (12): _consistency_score(), _extract_bail_decision(), extract_decision(), _extract_employment_decision(), _extract_welfare_decision(), _matches_any(), normalize_text(), P1RunScore (+4 more)

### Community 7 - "Demographics Config"
Cohesion: 0.29
Nodes (10): list_variants(), DemographicsError, get_variant_by_id(), get_variant_group(), load_demographics_config(), _optional_str(), Raised when demographics configuration is missing or invalid., Variant (+2 more)

### Community 8 - "Model Configuration"
Cohesion: 0.24
Nodes (9): list_models(), ConfigError, load_model_config(), load_models_config(), ModelConfig, Raised when configuration files are missing or invalid., Backwards-compatible alias for loading all model configurations.      Kept for c, test_get_model_config() (+1 more)

### Community 9 - "Benchmark Reports"
Cohesion: 0.33
Nodes (10): Demographic Consistency Pillar, Pressure Mode Benchmark Run, Baseline Mode Benchmark Run, Deepseek-V3 Model, Baseline Latency Metric, Pressure Latency Metric, Baseline Mode, Pressure Mode (+2 more)

### Community 10 - "Scenario Loader"
Cohesion: 0.28
Nodes (6): load_scenario(), _optional_str(), Raised when a scenario file is missing or invalid., ScenarioLoadError, Scenario, test_load_scenario()

### Community 11 - "Package Initializers"
Cohesion: 0.4
Nodes (1): Engine layer for model execution and orchestration.

### Community 12 - "Graph Reporting"
Cohesion: 0.5
Nodes (4): AggregateScoreError Exception, AggregatedRunScore Result Type, Build Run Report Function, DbConfig Database Configuration

### Community 13 - "Test Fixtures"
Cohesion: 0.67
Nodes (2): pytest_configure(), Ensure `src/` is importable when running tests without installing it.      This

### Community 14 - "P2 Scoring"
Cohesion: 0.67
Nodes (2): P2RunScore, P2ScenarioScore

### Community 15 - "Contributing Guide"
Cohesion: 0.67
Nodes (3): Code Quality Requirements, Conventional Commits, Contributing Workflow

### Community 16 - "Entry Point"
Cohesion: 1.0
Nodes (0): 

### Community 17 - "Provider Interface"
Cohesion: 1.0
Nodes (2): Database Connection Function, OpenRouterClient API Client

### Community 18 - "Template Interface"
Cohesion: 1.0
Nodes (2): Run Single Template Variant Function, ScenarioTemplate Template Class

### Community 19 - "Path Definitions"
Cohesion: 1.0
Nodes (0): 

### Community 20 - "Package Root"
Cohesion: 1.0
Nodes (0): 

### Community 21 - "DB Init"
Cohesion: 1.0
Nodes (0): 

### Community 22 - "IRBG Overview"
Cohesion: 1.0
Nodes (1): Institutional Readiness & Bias Benchmark for Governance

### Community 23 - "Vaani Reference"
Cohesion: 1.0
Nodes (1): Vaani Voice Dictation App

### Community 24 - "Graph Report"
Cohesion: 1.0
Nodes (1): IRBG Knowledge Graph

## Knowledge Gaps
- **27 isolated node(s):** `Ensure `src/` is importable when running tests without installing it.      This`, `Raised when configuration files are missing or invalid.`, `Backwards-compatible alias for loading all model configurations.      Kept for c`, `Raised when demographics configuration is missing or invalid.`, `Raised when a run cannot be aggregated.` (+22 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Entry Point`** (2 nodes): `main()`, `main.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Provider Interface`** (2 nodes): `Database Connection Function`, `OpenRouterClient API Client`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Template Interface`** (2 nodes): `Run Single Template Variant Function`, `ScenarioTemplate Template Class`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Path Definitions`** (1 nodes): `paths.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Package Root`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `DB Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `IRBG Overview`** (1 nodes): `Institutional Readiness & Bias Benchmark for Governance`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Vaani Reference`** (1 nodes): `Vaani Voice Dictation App`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Graph Report`** (1 nodes): `IRBG Knowledge Graph`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `run_single_template_variant()` connect `Execution Runner` to `Database Layer`, `Template Engine`, `LLM Provider`, `CLI & Commands`?**
  _High betweenness centrality (0.090) - this node is a cross-community bridge._
- **Why does `load_scenario_template()` connect `Template Engine` to `Execution Runner`?**
  _High betweenness centrality (0.086) - this node is a cross-community bridge._
- **Why does `score_p1_run()` connect `Database Layer` to `CLI & Commands`, `P1 Consistency Scoring`?**
  _High betweenness centrality (0.071) - this node is a cross-community bridge._
- **Are the 17 inferred relationships involving `connect()` (e.g. with `test_build_run_report()` and `test_insert_model_run_and_response()`) actually correct?**
  _`connect()` has 17 INFERRED edges - model-reasoned connections that need verification._
- **Are the 14 inferred relationships involving `run_single_template_variant()` (e.g. with `run_template_variant()` and `get_model_config()`) actually correct?**
  _`run_single_template_variant()` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `run_template_folder()` (e.g. with `run_template_folder_cmd()` and `get_model_config()`) actually correct?**
  _`run_template_folder()` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 16 inferred relationships involving `DbConfig` (e.g. with `test_build_run_report()` and `test_insert_model_run_and_response()`) actually correct?**
  _`DbConfig` has 16 INFERRED edges - model-reasoned connections that need verification._