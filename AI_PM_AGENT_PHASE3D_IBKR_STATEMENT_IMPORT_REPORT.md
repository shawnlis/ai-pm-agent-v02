# AI PM Agent Phase 3D IBKR Statement Import Report

Date: 2026-06-08

Branch: `feature/phase3d-ibkr-statement-import-adapter`

Base: `v0.2-private-portfolio-exposure` / `c3f0b71`

## Summary

This branch adds a narrow Phase 3D offline IBKR statement import adapter. The adapter reads local IBKR-exported CSV or Flex-style CSV files and writes review artifacts plus a Phase 3C-compatible holdings CSV.

This is an import-review tool only. It does not connect to IBKR, use broker APIs, inspect credentials, run live workflows, parse PDFs, alter PM decision logic, or wire portfolio data into PM recommendations.

## Files Added

- `src/ai_pm_agent/portfolio/ibkr_import.py`
- `scripts/ibkr_statement_import.py`
- `examples/portfolio/ibkr_statement_sample.csv`
- `examples/portfolio/ibkr_flex_sectioned_sample.csv`
- `docs/IBKR_STATEMENT_IMPORT.md`
- `tests/test_ibkr_import.py`
- `AI_PM_AGENT_PHASE3D_IBKR_STATEMENT_IMPORT_REPORT.md`

## Outputs

The adapter writes:

- `parsed_holdings_review.csv`
- `portfolio_runner_ready_holdings.csv`
- `ibkr_import_warnings.md`
- `ibkr_import_summary.json`

The runner-ready CSV uses the Phase 3C holdings columns, but all rows remain review-required until a human checks the review CSV and warnings file.

## Supported Input

Supported:

- plain local CSV with one header row
- sectioned Flex-style local CSV with `Section,Header,...` and `Section,Data,...`
- Open Positions / Positions sections

Not supported:

- IBKR connection
- broker API
- credentials
- live prices or live FX
- PDF parsing
- trades/cash ledger conversion
- dashboard, scheduler, advisor, trading, or PM decision workflows

## Safety Boundaries

- No `ai_pm_agent.py` changes.
- No PM decision or recommendation logic changes.
- No portfolio-aware PM recommendation behavior.
- No live LLM, web search, yfinance, OpenRouter, DeepSeek, IBKR, broker, FX, market data, or ETF constituent workflow.
- No secret files inspected.

## Validation

Validation commands run:

```powershell
python -m py_compile .\ai_pm_agent.py
python -m py_compile .\src\ai_pm_agent\portfolio\models.py .\src\ai_pm_agent\portfolio\exposure.py .\src\ai_pm_agent\portfolio\fixtures.py .\src\ai_pm_agent\portfolio\runner.py .\src\ai_pm_agent\portfolio\ibkr_import.py .\src\ai_pm_agent\portfolio\__init__.py
python -m py_compile .\scripts\portfolio_exposure_report.py .\scripts\ibkr_statement_import.py
python -m pytest -q tests\test_portfolio_exposure.py tests\test_portfolio_models.py
python -m pytest -q tests\test_portfolio_runner.py
python -m pytest -q tests\test_ibkr_import.py
python -m pytest -q
```

Results:

- `ai_pm_agent.py` compile: passed
- portfolio module compile: passed
- adapter/script compile: passed
- existing portfolio tests: `31 passed, 2 subtests passed`
- Phase 3C runner tests: `11 passed`
- Phase 3D IBKR adapter tests: `9 passed`
- full pytest: `128 passed, 2 subtests passed`

## Sample Command

```powershell
python .\scripts\ibkr_statement_import.py `
  --statement .\examples\portfolio\ibkr_statement_sample.csv `
  --out-dir .\reports\ibkr_import

python .\scripts\ibkr_statement_import.py `
  --statement .\examples\portfolio\ibkr_flex_sectioned_sample.csv `
  --out-dir .\reports\ibkr_import_flex
```

Expected sample outputs:

- `reports/ibkr_import/parsed_holdings_review.csv`
- `reports/ibkr_import/portfolio_runner_ready_holdings.csv`
- `reports/ibkr_import/ibkr_import_warnings.md`
- `reports/ibkr_import/ibkr_import_summary.json`

Simple CSV sample result:

- review rows: `4`
- ready holdings: `3`
- excluded rows: `1`
- warnings: `4`
- excluded row reason: cash-like row requires manual review
- all ready rows include `IBKR_IMPORT_REVIEW_REQUIRED`

Flex-style sample result:

- review rows: `3`
- ready holdings: `3`
- excluded rows: `0`
- warnings: `3`
- all ready rows include `IBKR_IMPORT_REVIEW_REQUIRED`

Combined sample result when both sample files are imported together with explicit metadata:

- review rows: `7`
- ready holdings: `6`
- excluded rows: `1`
- warnings: `7`
- excluded row reason: cash-like row requires manual review
- all ready rows include `IBKR_IMPORT_REVIEW_REQUIRED` in notes

## Known Limitations

- The adapter does not verify imported holdings.
- Missing or blank trading currency is defaulted to base currency only for review convenience and produces explicit warnings.
- Cash-like rows are excluded and require manual review.
- Issuer canonical IDs and taxonomy metadata still need manual review/enrichment.
- Imported market values and FX-normalized values are trusted local statement inputs.
- PDF parsing is intentionally out of scope.

## Recommended Next Step

Review the local Phase 3D branch. If accepted, push and open a draft PR for review. Do not wire imported holdings into PM recommendations.
