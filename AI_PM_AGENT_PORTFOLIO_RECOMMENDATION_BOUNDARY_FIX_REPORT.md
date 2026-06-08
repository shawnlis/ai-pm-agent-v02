# AI PM Agent Portfolio Recommendation Boundary Fix Report

Date: 2026-06-08

Branch: `feature/portfolio-recommendation-boundary-fix`

Base: `v0.3-private-ibkr-import-adapter` / `85a8371`

## Issue Summary

GPT Pro audit found that the legacy root `ai_pm_agent.py` could read `portfolio.csv`, format it as `## Current Portfolio`, pass it through `portfolio_md` into `build_pm_prompt()`, and send the resulting prompt to `call_llm("Deep PM Agent", memo_prompt)`.

That violated the documented boundary that Phase 3 portfolio data is offline/reporting-only and must not influence PM recommendations, PM memos, or LLM decision prompts.

## Files Changed

- `ai_pm_agent.py`
- `tests/test_portfolio_recommendation_boundary.py`
- `AI_PM_AGENT_PORTFOLIO_RECOMMENDATION_BOUNDARY_FIX_REPORT.md`

## Exact Path Removed

Removed from the PM recommendation path:

1. `run_company_research()` no longer calls `read_portfolio(portfolio_path)`.
2. `run_company_research()` no longer passes `portfolio_md` into `build_pm_prompt()`.
3. `build_pm_prompt()` no longer accepts a `portfolio_md` parameter.
4. `build_pm_prompt()` no longer includes a `Current portfolio:` section.
5. `call_llm("Deep PM Agent", memo_prompt)` now receives a prompt with no current-holdings payload.
6. `full_research_package.md` now receives a boundary note instead of portfolio holdings.

`portfolio_context.md` is still written, but it now contains only a safety-boundary note:

`Portfolio context is disabled for PM recommendations; use offline portfolio exposure reports instead.`

## Legacy Helper Handling

`read_portfolio()` remains in `ai_pm_agent.py` as a legacy diagnostics-only helper. It is documented as intentionally unused by PM prompt, PM memo, or recommendation paths.

The legacy `--portfolio` CLI option remains accepted for backward compatibility, but its help text states it is a no-op for PM recommendations and points users to offline portfolio exposure reports.

## Tests Added

Added `tests/test_portfolio_recommendation_boundary.py`.

Coverage:

- `build_pm_prompt()` output does not contain `Current Portfolio`.
- `build_pm_prompt()` output does not contain fake portfolio tickers or holdings.
- `run_company_research()` does not call `read_portfolio()` in the PM path.
- `run_company_research()` does not pass fake portfolio holdings into the `Deep PM Agent` prompt.
- `portfolio.csv` can exist on disk while PM prompt artifacts remain portfolio-free.
- `portfolio_context.md` contains only the disabled-boundary notice.

## Grep / Search Results

Searches excluded `_local_archive/`, `_archive/`, `archive/`, `reports/`, and `external_reference_repos/`.

### `Current Portfolio`

- `ai_pm_agent.py:1247` - diagnostics-only legacy `read_portfolio()` output.
- `tests/test_portfolio_recommendation_boundary.py:73` - test fixture proving legacy diagnostics can still format portfolio data.
- `tests/test_portfolio_recommendation_boundary.py:96` - negative assertion for PM prompt.
- `tests/test_portfolio_recommendation_boundary.py:193` - negative assertion for Deep PM prompt.

Classification: removed from PM path; diagnostics-only and tests.

### `portfolio_md`

- No remaining references.

Classification: removed from PM path.

### `portfolio_context`

- `ai_pm_agent.py:1262` - disabled boundary notice helper.
- `ai_pm_agent.py:7327` - boundary note assigned in `run_company_research()`.
- `ai_pm_agent.py:7328` - writes `portfolio_context.md` with boundary note only.
- `tests/test_portfolio_recommendation_boundary.py:66` - test name.
- `tests/test_portfolio_recommendation_boundary.py:201` - test reads boundary artifact.

Classification: output artifact only; contains no holdings.

### `portfolio_fit`

- `ai_pm_agent.py:4264` - legacy structured JSON schema field.
- `ai_pm_agent.py:4314` - required-field list.
- `ai_pm_agent.py:4411` - decision text blob field extraction.
- `ai_pm_agent.py:4842` - peer comparison payload field.
- `ai_pm_agent.py:5611` - fallback decision text: `No reliable portfolio view.`
- `ai_pm_agent.py:8294` - validation mock payload.
- `tests/test_portfolio_recommendation_boundary.py:44` - test decision fixture.

Classification: schema/output field only; no current holdings are injected.

### `read_portfolio`

- `ai_pm_agent.py:1232` - legacy diagnostics-only helper.
- `tests/test_portfolio_recommendation_boundary.py:72` - test exercises diagnostics helper.
- `tests/test_portfolio_recommendation_boundary.py:117` - test fails if PM path calls helper.

Classification: diagnostics-only and tests; removed from PM path.

### `portfolio.csv`

- `ai_pm_agent.py:1241` - diagnostics-only missing-file message.
- `ai_pm_agent.py:1246` - diagnostics-only empty-file message.
- `ai_pm_agent.py:1259` - diagnostics-only read-error message.
- `ai_pm_agent.py:1267` - boundary notice says legacy input is not read or injected.
- `ai_pm_agent.py:8732` - legacy `single --portfolio` no-op option help.
- `ai_pm_agent.py:8744` - legacy `batch --portfolio` no-op option help.
- `ai_pm_agent.py:8773` - legacy `abtest-chokepoint --portfolio` no-op option help.
- `tests/test_portfolio_recommendation_boundary.py:69` - fake file fixture.
- `tests/test_portfolio_recommendation_boundary.py:106` - fake file fixture.

Classification: diagnostics-only, no-op CLI compatibility, and tests.

## Remaining Portfolio Reference Classification

- Removed from PM path: `portfolio_md`, `Current portfolio:` prompt block, `read_portfolio()` call in `run_company_research()`.
- Diagnostics-only: `read_portfolio()`, `Current Portfolio` legacy formatting.
- Output artifact only: `portfolio_context.md` boundary note.
- Test fixture: fake `portfolio.csv`, `TQQQ`, `SOXL`, negative prompt assertions.
- Schema/output field only: `portfolio_fit`.
- Still risky: none found.

## Validation

Commands run:

```powershell
python -m py_compile .\ai_pm_agent.py
python -m py_compile .\src\ai_pm_agent\portfolio\models.py .\src\ai_pm_agent\portfolio\exposure.py .\src\ai_pm_agent\portfolio\fixtures.py .\src\ai_pm_agent\portfolio\runner.py .\src\ai_pm_agent\portfolio\ibkr_import.py .\src\ai_pm_agent\portfolio\__init__.py
python -m py_compile .\scripts\portfolio_exposure_report.py
python -m py_compile .\scripts\ibkr_statement_import.py
python -m pytest -q
python -m pytest -q tests\test_portfolio_exposure.py tests\test_portfolio_models.py
python -m pytest -q tests\test_portfolio_runner.py
python -m pytest -q tests\test_ibkr_import.py
```

Results:

- compile checks: passed
- full pytest: `130 passed, 1 warning, 2 subtests passed`
- portfolio exposure/model tests: `31 passed, 2 subtests passed`
- portfolio runner tests: `11 passed`
- IBKR import tests: `9 passed`
- new boundary tests: `2 passed`

## Safety Confirmations

- Portfolio data cannot enter the PM prompt by default.
- `call_llm("Deep PM Agent", memo_prompt)` no longer receives current holdings.
- PM recommendation logic remains portfolio-independent.
- Offline portfolio exposure runner tests still pass.
- Offline IBKR adapter tests still pass.
- No live API, LLM, web search, yfinance, OpenRouter, DeepSeek, IBKR, broker, or external workflow was run.
- No secrets, `.env`, `Openrouter.txt`, API keys, tokens, or broker credentials were inspected.
- No dashboard, scheduler, FastAPI, advisor copilot, trading feature, live IBKR, or PDF parser was added.

## Recommended Next Action

Review this branch, then push and open a PR if accepted. Keep the PR scoped to the portfolio recommendation boundary fix only.
