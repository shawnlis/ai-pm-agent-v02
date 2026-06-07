# AI PM Agent Phase 3 Portfolio Schema Exposure Report

Report date: 2026-06-07

## Baseline

- Baseline tag: `v0.1-private-offline-db`
- Baseline commit: `ef9638f`
- Branch: `feature/phase3-portfolio-schema-exposure`
- Worktree: `C:\Users\Lenovo\ai_pm_agent_v02_phase3_portfolio`

This branch was created from the validated v0.1 baseline. The original dirty `master` worktree at `C:\Users\Lenovo\ai_pm_agent_v02` was not merged, reset, cleaned, stashed, committed, pushed, or overwritten.

## Files Ported

Approved portfolio source files:

- `src/ai_pm_agent/portfolio/__init__.py`
- `src/ai_pm_agent/portfolio/models.py`
- `src/ai_pm_agent/portfolio/exposure.py`
- `src/ai_pm_agent/portfolio/fixtures.py`

Approved docs and tests:

- `docs/PORTFOLIO_SCHEMA.md`
- `tests/test_portfolio_exposure.py`
- `tests/test_portfolio_models.py`

## Files Intentionally Excluded

The following dirty-WIP files and local artifacts were intentionally not ported:

- `AI_PM_AGENT_EXTERNAL_BENCHMARK_AUDIT.md`
- `AI_PM_AGENT_GAP_AUDIT.md`
- `AI_PM_AGENT_LOCAL_WIP_AUDIT.md`
- `external_reference_repos/`
- `outputs/`
- `reports/`
- SQLite database files
- `.env`
- `Openrouter.txt`
- API keys, tokens, credentials, browser state, caches, and other secret-like files

`.gitignore` was inspected but left unchanged. The v0.1 baseline already includes the hardening ignore rules needed for this branch, and the portfolio schema/tests do not require additional ignore entries.

## What This Branch Adds

This branch adds non-invasive portfolio-awareness groundwork:

- `Holding` model with ticker normalization, optional valuation data, asset class, themes, risk bucket, and leverage multiplier.
- `PortfolioSnapshot` model with cash, holdings, benchmark, total market value, total equity value, gross exposure, leverage-adjusted exposure, holding weights, and exposure buckets.
- Deterministic handling for:
  - `TQQQ` and `SOXL` defaulting to `3.0` leverage multipliers.
  - `ETHA` defaulting to `crypto_etf`, `crypto beta`, and `crypto_beta`.
- Pure exposure helper functions for market value, weights, gross exposure, leverage-adjusted exposure, theme, asset-class, currency, risk-bucket exposure, and incomplete valuation holdings.
- Fake deterministic fixture data for portfolio model tests.
- Portfolio schema documentation.

## Validation Commands

Commands run in the clean Phase 3 worktree:

```powershell
git status -sb
python -m py_compile .\ai_pm_agent.py
python -m py_compile .\src\ai_pm_agent\portfolio\*.py
python -m py_compile .\src\ai_pm_agent\portfolio\__init__.py .\src\ai_pm_agent\portfolio\models.py .\src\ai_pm_agent\portfolio\exposure.py .\src\ai_pm_agent\portfolio\fixtures.py
python -m pytest -q tests\test_portfolio_exposure.py tests\test_portfolio_models.py
python -m pytest -q
```

Note: the literal wildcard form of `python -m py_compile .\src\ai_pm_agent\portfolio\*.py` fails on this Windows shell because Python receives the wildcard unexpanded. The equivalent explicit file compile command passed.

## Test Results

- `python -m py_compile .\ai_pm_agent.py`: passed.
- Explicit portfolio `py_compile`: passed.
- Targeted portfolio pytest: `17 passed, 2 subtests passed`.
- Full project pytest: `94 passed, 2 subtests passed`.

No `external_reference_repos/` tests were collected in this clean branch.

## Safety Checks

- `ai_pm_agent.py` was untouched.
- PM decision and recommendation logic were untouched.
- No live LLM, OpenRouter, DeepSeek, web search, yfinance research, or other live API workflow was run.
- No secrets were inspected.
- `.env`, `Openrouter.txt`, API keys, tokens, and credential files were not opened.
- No dashboard, scheduler, FastAPI, advisor, quant, or live research feature was added.

## Known Limitations

- This is schema/exposure groundwork only.
- There is no real holdings loader yet.
- There is no portfolio source of truth yet.
- There is no FX conversion engine; currency exposure is computed from supplied market values.
- There is no portfolio price refresh.
- There is no beta, correlation, VaR/CVaR, drawdown, or scenario stress engine.
- The portfolio snapshot is not connected to `ai_pm_agent.py`, PM prompts, generated PM decisions, SQLite, or reports.

## Next Recommended Step

Keep this branch narrow. The next Phase 3 slice should add a fixture-backed portfolio loader and offline portfolio risk snapshot report without modifying `ai_pm_agent.py` or PM recommendation logic.

Suggested next task:

```text
Add a non-live portfolio CSV/JSON loader and an offline portfolio risk snapshot report using the existing Holding and PortfolioSnapshot models. Use fixture/local files only, keep real portfolio files ignored, do not call yfinance or LLMs, and do not feed the portfolio snapshot into PM decisions yet.
```
