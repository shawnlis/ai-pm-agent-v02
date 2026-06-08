# AI PM Agent Phase 3C Offline Portfolio Input Runner Report

Date: 2026-06-08

Branch: `feature/phase3c-offline-portfolio-input-runner`

Base: `origin/master` at `399ae13`

## Summary

This branch adds a narrow offline portfolio input runner for Phase 3C. The runner turns local static CSV or JSON inputs into Markdown and JSON exposure reports using the existing Phase 3B portfolio models and exposure helpers.

This is a local reporting tool only. It does not modify `ai_pm_agent.py`, PM decision logic, PM recommendation logic, research execution, or company DB behavior.

## Files Added

- `src/ai_pm_agent/portfolio/runner.py`
- `scripts/portfolio_exposure_report.py`
- `examples/portfolio/holdings_sample.csv`
- `examples/portfolio/issuer_mapping_sample.csv`
- `examples/portfolio/taxonomy_mapping_sample.csv`
- `examples/portfolio/manual_lookthrough_sample.csv`
- `examples/portfolio/fx_snapshot_sample.csv`
- `docs/PORTFOLIO_INPUT_RUNNER.md`
- `tests/test_portfolio_runner.py`
- `AI_PM_AGENT_PHASE3C_OFFLINE_PORTFOLIO_INPUT_RUNNER_REPORT.md`

## Input Formats

The runner supports CSV and JSON row inputs for:

- holdings
- issuer mapping
- taxonomy mapping
- manual look-through
- FX snapshot

The sample files use fake/static values only and do not contain private account data.

## Command

```powershell
python .\scripts\portfolio_exposure_report.py `
  --holdings examples\portfolio\holdings_sample.csv `
  --issuer-mapping examples\portfolio\issuer_mapping_sample.csv `
  --taxonomy-mapping examples\portfolio\taxonomy_mapping_sample.csv `
  --manual-lookthrough examples\portfolio\manual_lookthrough_sample.csv `
  --fx-snapshot examples\portfolio\fx_snapshot_sample.csv `
  --out reports\portfolio_exposure_report.md `
  --json-out reports\portfolio_exposure_summary.json
```

The `reports/` directory is ignored by Git.

## Runner Behavior

The runner:

- reads local files only
- validates required holdings columns
- validates numeric fields
- builds a `PortfolioSnapshot`
- applies optional issuer and taxonomy mappings deterministically
- applies optional FX snapshots deterministically
- keeps line-item exposure and manual look-through exposure separate
- emits warnings for missing inputs, missing mappings, missing FX, missing base values, and look-through weights not summing to 100%
- writes Markdown and JSON summaries

## Safety Boundaries

- No PM decision logic changed.
- No recommendation logic changed.
- No portfolio-aware PM recommendations were added.
- No live LLM, web search, yfinance, OpenRouter, DeepSeek, broker, FX, market data, or constituent-fetch workflow was run or added.
- No scheduler, dashboard, FastAPI, advisor copilot, quant integration, or live research feature was added.
- No secrets were inspected.

## Validation

Validation commands run:

```powershell
python -m py_compile .\ai_pm_agent.py
python -m py_compile .\src\ai_pm_agent\portfolio\models.py .\src\ai_pm_agent\portfolio\exposure.py .\src\ai_pm_agent\portfolio\fixtures.py
python -m py_compile .\src\ai_pm_agent\portfolio\runner.py .\scripts\portfolio_exposure_report.py
python -m pytest -q tests\test_portfolio_exposure.py tests\test_portfolio_models.py
python -m pytest -q tests\test_portfolio_runner.py
python -m pytest -q
```

Results:

- `ai_pm_agent.py` compile: passed
- portfolio module compile: passed
- runner compile: passed
- targeted portfolio tests: `31 passed, 2 subtests passed`
- runner tests: `9 passed`
- full pytest: `117 passed, 2 subtests passed`

Sample command run:

```powershell
python .\scripts\portfolio_exposure_report.py --holdings examples\portfolio\holdings_sample.csv --issuer-mapping examples\portfolio\issuer_mapping_sample.csv --taxonomy-mapping examples\portfolio\taxonomy_mapping_sample.csv --manual-lookthrough examples\portfolio\manual_lookthrough_sample.csv --fx-snapshot examples\portfolio\fx_snapshot_sample.csv --out reports\portfolio_exposure_report.md --json-out reports\portfolio_exposure_summary.json
```

Sample outputs:

- `reports/portfolio_exposure_report.md`
- `reports/portfolio_exposure_summary.json`

## Known Limitations

- Input values are trusted local/static values.
- FX values are user supplied and not live-market verified.
- Manual look-through is user supplied and not fetched.
- Multi-currency cash is not modeled.
- Taxonomy values remain local strings.
- The output is informational exposure reporting only, not advice or a risk model.

## Recommended Next Step

Review the local branch. If accepted, push and open a draft PR for Phase 3C review. Do not wire portfolio inputs into PM recommendations.
