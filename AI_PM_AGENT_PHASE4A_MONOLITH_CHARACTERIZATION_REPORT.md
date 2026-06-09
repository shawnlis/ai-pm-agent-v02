# AI PM Agent Phase 4A Monolith Characterization Report

## Executive Verdict

`ai_pm_agent.py` is ready for planned modularization, but not for a broad refactor in one PR.

The current file is a working monolith with approximately 7,966 lines and 208 top-level function definitions. It mixes CLI parsing, yfinance market-data retrieval, web-search adapters, LLM prompt builders, LLM calls, evidence/fact-cache handling, valuation/guardrail logic, workflow orchestration, and artifact writing.

Phase 4A made no production code or behavior changes. It adds characterization tests and this architecture report so future extraction can be done behind stable behavioral boundaries.

## Current Monolith Inventory

### Major Function Groups

- Utility and formatting helpers: `now_str`, `today_str`, `ensure_dir`, `save_text`, `save_json`, markdown/table formatting, numeric formatting, retry helpers.
- Data-fetch diagnostics: fetch diagnostic shape, fetch diagnostic summaries, market-data reliability scoring.
- Market data: yfinance snapshot assembly, price sanity checks, macro snapshot.
- Portfolio legacy boundary: `read_portfolio` remains diagnostics-only; `disabled_portfolio_context_notice` is the active PM-path boundary artifact.
- Watchlist handling: watchlist read/upsert helpers and ticker normalization.
- Web search and evidence: search provider selection, API key checks, evidence query builders, source classification, evidence diagnostics.
- Fact cache: SQLite schema, TTL, extraction prompt, extraction call, save/load/report helpers.
- Valuation and quality: price sanity, valuation scenarios, industry valuation bridge, quality report, PM guardrails.
- Peer context: peer discovery prompt, LLM discovery, peer selection, relative valuation rendering.
- Prompt builders: PM memo, structured JSON, comparative ranking, fact extraction, peer discovery, Chokepoint Scout.
- Chokepoint workflow: scout prompt/JSON prompt, fallback/repair, weighted overlay, A/B test runner.
- Summary/logging: research log flattening, batch summary, quality classification.
- Workflow orchestration: `run_company_research`, `run_single`, `run_batch`, `run_fact_scout`, `run_chokepoint_abtest`, `run_validation`.
- CLI entrypoint: `main`.

### Prompt Builders

Prompt builders currently live in the root file:

- `build_fact_extraction_prompt`
- `build_peer_discovery_prompt`
- `build_pm_prompt`
- `build_json_prompt`
- `build_comparative_ranking_prompt`
- `build_chokepoint_scout_prompt`
- `build_chokepoint_json_prompt`

The safest first extraction seam is this group because these functions are mostly deterministic string builders when given explicit inputs.

### LLM Call Boundaries

External LLM calls are centralized through:

- `openrouter_client`
- `deepseek_client`
- `get_llm_client_and_model`
- `call_llm`

The workflow invokes `call_llm` from several paths:

- Fact Extraction Agent
- Peer Discovery Agent
- Chokepoint Scout
- Chokepoint JSON Agent
- Deep PM Agent
- Structured JSON Agent
- JSON repair
- Comparative Ranking Agent

These should not be moved before prompt builders and artifact naming are characterized, because LLM calls sit on the behavioral boundary between deterministic local code and live external services.

### File And Artifact Writers

Root helper writers:

- `save_text`
- `save_json`
- direct `DataFrame.to_csv` calls

Important workflow artifacts written by `run_company_research` include:

- `market_snapshot.json`
- `market_snapshot.md`
- `macro_snapshot.md`
- `peer_context.md`
- `evidence_context.md`
- `evidence_diagnostics.json`
- `fact_cache_report_before.json`
- `fact_cache_report_before.md`
- `fresh_facts.json`
- `cached_facts_used.json`
- `cached_facts.md`
- `fact_cache_report_after.json`
- `fact_cache_report_after.md`
- `ai_agent_demand_framework.md`
- `portfolio_context.md`
- `memo_prompt.md`
- `pm_memo.md`
- `llm_diagnostics.json`
- `pm_decision.json`
- `quality_report.md`
- `full_research_package.md`
- `research_log.csv`

Artifact writing is a good second extraction seam, after prompt builders, because artifact names and output package composition should remain stable.

### CLI Entrypoints

`main` exposes:

- `single`
- `batch`
- `log`
- `scout`
- `abtest-chokepoint`
- `validate`

The `--portfolio` option remains on legacy CLI paths but is documented as no-op for PM recommendations.

### External Data And API Call Points

No live external workflows were run for Phase 4A. Static inspection identified these production call boundaries:

- yfinance via `yf.Ticker` in market snapshot, macro proxy, best financial info, peer metrics.
- HTTP search providers through `urllib.request.urlopen` in `http_json_request`.
- LLM providers through `call_llm`, OpenRouter client, and DeepSeek client.
- SQLite fact cache through `sqlite3.connect`.
- Local file writes through `save_text`, `save_json`, and `to_csv`.

These boundaries need explicit dependency injection or wrappers before deeper workflow extraction.

### Portfolio References

Current root portfolio references are:

- `read_portfolio`: legacy diagnostics-only helper. It can still render `## Current Portfolio` when called directly, but it is not used by PM prompt, memo, or recommendation paths.
- `disabled_portfolio_context_notice`: active PM-path boundary notice.
- `run_company_research` Step 6: writes `portfolio_context.md` containing the disabled-boundary notice only.
- CLI `--portfolio`: legacy no-op compatibility option.
- `build_pm_prompt`: includes explicit portfolio independence instruction and has no portfolio parameter.

No route was found from portfolio CSV or IBKR import outputs into PM prompt construction.

### DB / Offline Research References

Root monolith DB behavior is mainly the fact cache:

- `FACT_CACHE_PATH`
- `fact_cache_db_path`
- `ensure_fact_cache_schema`
- `save_fact_cache_records`
- `load_cached_facts`
- `build_fact_cache_report`
- `run_fact_scout`

The separate company DB package under `src/ai_pm_agent/company_db/` is outside this root monolith extraction pass. The root workflow still produces artifact folders consumed by offline import/reporting tools, so artifact naming must remain stable.

## Current Monolith Risks

- One file owns too many responsibilities, making small behavioral changes hard to review.
- Prompt construction is interleaved with workflow orchestration and artifact writing.
- Live provider boundaries are not isolated enough for easy offline mocking.
- Artifact file naming is spread across orchestration code.
- Fact-cache side effects and LLM calls share the same workflow path.
- CLI compatibility options can outlive their behavior, as seen with legacy `--portfolio`.
- Future refactors could accidentally reintroduce portfolio context into PM prompts if prompt signatures are not locked down.

## Safe Extraction Seams

### Safe First Seam: Prompt Builders

Candidate module:

- `src/ai_pm_agent/research/prompts.py`

Rationale:

- Mostly pure string builders.
- Easy to test with small explicit inputs.
- Existing Phase 4A tests now lock the PM prompt signature and portfolio independence instruction.
- Extraction can initially re-export functions or import them from the new module without changing behavior.

### Safe Second Seam: Artifact Writers

Candidate module:

- `src/ai_pm_agent/research/artifacts.py`

Rationale:

- Artifact names are stable and user-visible.
- Centralizing artifact names can reduce future package-drift risk.
- Should be done after prompt extraction so prompt artifacts can be tested separately.

### Safe Third Seam: Workflow Orchestration

Candidate module:

- `src/ai_pm_agent/research/workflow.py`

Rationale:

- `run_company_research`, `run_single`, and `run_batch` are high-value seams but touch external data, LLM calls, fact cache, and artifacts.
- Extraction should wait until prompts and artifact writing are stable and covered.

### Final Seam: Thin Root Wrapper

Candidate endpoint:

- keep `ai_pm_agent.py` as a thin CLI/orchestration wrapper

Rationale:

- Preserves existing command compatibility.
- Lets lower-level modules own deterministic components.

## Unsafe Extraction Areas

Do not extract these first:

- `run_company_research` as a first move. It has too many side effects and provider calls.
- `call_llm` without first stabilizing prompt builders. Provider behavior and JSON fallback are sensitive.
- PM guardrails and decision repair logic without dedicated scoring/decision regression tests.
- Fact cache persistence without SQLite fixture tests covering migration and TTL behavior.
- CLI argument behavior without command-level compatibility tests.
- Portfolio/IBKR output plumbing into PM workflows. That boundary must remain disabled.

## Recommended Extraction Order

### Phase 4B

Extract prompt builders into:

- `src/ai_pm_agent/research/prompts.py`

Scope:

- Move deterministic prompt builders only.
- Preserve function names/signatures.
- Add focused prompt tests.
- Do not change prompt content.

### Phase 4C

Extract artifact/file writing into:

- `src/ai_pm_agent/research/artifacts.py`

Scope:

- Centralize artifact filenames and write helpers.
- Preserve output artifact names and package composition.
- Add tests for artifact naming and package sections.

### Phase 4D

Extract research workflow orchestration into:

- `src/ai_pm_agent/research/workflow.py`

Scope:

- Move `run_company_research` and related orchestration after prompt/artifact seams are stable.
- Keep live provider calls injectable or monkeypatchable.

### Phase 4E

Reduce `ai_pm_agent.py` into a thin CLI/orchestration wrapper.

Scope:

- Preserve `python ai_pm_agent.py ...` CLI compatibility.
- Keep legacy `--portfolio` as no-op unless explicitly removed in a later breaking cleanup.

## Tests Added

Added:

- `tests/test_phase4a_monolith_characterization.py`

Coverage:

- `build_pm_prompt` signature remains stable and excludes portfolio/holdings parameters.
- PM prompt contains the portfolio independence instruction.
- PM prompt does not contain `Current Portfolio`, `portfolio_md`, or sample holdings.
- Disabled portfolio context notice remains diagnostics-only and holdings-free.

Updated:

- `tests/test_portfolio_recommendation_boundary.py`

Coverage added:

- `full_research_package.md` must include the disabled portfolio boundary notice, not holdings.

## Validation Results

Initial focused characterization validation:

```powershell
python -m pytest -q tests\test_phase4a_monolith_characterization.py tests\test_portfolio_recommendation_boundary.py
```

Result:

- `5 passed, 1 warning`

Final Phase 4A validation:

```powershell
python -m py_compile .\ai_pm_agent.py
python -m py_compile .\src\ai_pm_agent\portfolio\models.py .\src\ai_pm_agent\portfolio\exposure.py .\src\ai_pm_agent\portfolio\fixtures.py .\src\ai_pm_agent\portfolio\runner.py .\src\ai_pm_agent\portfolio\ibkr_import.py .\src\ai_pm_agent\portfolio\__init__.py
python -m py_compile .\scripts\portfolio_exposure_report.py
python -m py_compile .\scripts\ibkr_statement_import.py
python -m pytest -q tests\test_portfolio_recommendation_boundary.py
python -m pytest -q tests\test_ibkr_import.py
python -m pytest -q
```

Results:

- portfolio recommendation boundary tests: `2 passed, 1 warning`
- IBKR import tests: `10 passed`
- full pytest: `134 passed, 1 warning, 2 subtests passed`

## Safety Boundary Confirmation

Phase 4A did not:

- modify production code
- modify PM decision or recommendation logic
- wire portfolio data into PM decisions
- reintroduce portfolio data into PM prompts
- run live LLM/API/web/yfinance/OpenRouter/DeepSeek/IBKR/broker workflows
- inspect `.env`, `Openrouter.txt`, API keys, tokens, broker credentials, or secret files
- add IBKR automation
- add Flex Web Service download
- add PDF parsing
- add dashboard, scheduler, FastAPI, advisor, quant, trading, sizing, or recommendation features

## Explicit Do-Not-Build List

Do not build in Phase 4:

- IBKR automation
- IBKR Flex Web Service downloader
- PDF parser
- broker API integration
- live IBKR connection
- trading or order submission
- dashboard
- scheduler
- FastAPI service
- advisor copilot
- quant integration
- portfolio-aware PM recommendations
- any path that injects portfolio holdings into PM prompts or PM memos

## Exact Recommended Next Action

Open Phase 4A as a safety/architecture characterization PR only. If accepted, start Phase 4B as a separate PR that extracts prompt builders into `src/ai_pm_agent/research/prompts.py` while preserving signatures and prompt content.
