# AI PM Agent Phase 3B Portfolio Metadata Exposure Report

Date: 2026-06-08

Branch: `feature/phase3b-portfolio-metadata-exposure`

Base: `origin/master` at `e3e9770`

## Summary

This branch adds a narrow Phase 3B metadata and pure exposure-helper layer for portfolio analysis.

The change is additive and local-only. It does not wire portfolio data into PM recommendations, rating changes, action changes, company research execution, or company database behavior.

## Files Modified

- `src/ai_pm_agent/portfolio/models.py`
- `src/ai_pm_agent/portfolio/exposure.py`
- `src/ai_pm_agent/portfolio/__init__.py`
- `src/ai_pm_agent/portfolio/fixtures.py`
- `tests/test_portfolio_models.py`
- `tests/test_portfolio_exposure.py`
- `docs/PORTFOLIO_SCHEMA.md`

## Files Added

- `AI_PM_AGENT_PHASE3B_PORTFOLIO_METADATA_EXPOSURE_REPORT.md`

## Model Fields Added

`Holding` now supports optional metadata for:

- `instrument_type`
- `issuer_name`
- `issuer_canonical_id`
- `underlying_issuer_name`
- `underlying_ticker`
- `listing_country`
- `country_of_risk`
- `region`
- `sector`
- `industry`
- `trading_currency`
- `base_currency`
- `fx_rate_to_base`
- `market_value_local`
- `market_value_base`
- `leverage_factor`
- `lookthrough_available`
- `lookthrough_source`
- `lookthrough_components`

`LookThroughComponent` was added for manually supplied look-through metadata:

- `holding_ticker`
- `component_issuer_name`
- `component_issuer_canonical_id`
- `component_ticker`
- `component_weight`
- `sector`
- `industry`
- `country_of_risk`
- `region`
- `theme`
- `instrument_type`
- `source_note`

## Helper Functions Added

- `calculate_base_market_value`
- `calculate_base_market_value_exposure`
- `calculate_leverage_adjusted_gross_exposure`
- `calculate_base_leverage_adjusted_gross_exposure`
- `calculate_sector_exposure`
- `calculate_industry_exposure`
- `calculate_region_exposure`
- `calculate_country_of_risk_exposure`
- `calculate_issuer_exposure`
- `calculate_instrument_type_exposure`
- `calculate_concentration_summary`
- `calculate_lookthrough_exposure`
- `calculate_lookthrough_sector_exposure`

Existing exposure helpers remain available.

## Fixture Coverage

The sample portfolio fixture now includes fake/local metadata coverage for:

- `TQQQ`
- `SOXL`
- `7709.HK`
- `HY9H`
- `TSLA`
- `GOOGL`
- `MSFT`
- `ETHA`
- `NVDA`
- `SMS`

The fixture uses fake values only. It does not use live prices, live FX, live ETF constituents, web search, yfinance, or API calls.

## Tests Added Or Updated

Coverage now includes:

- optional metadata fields
- `themes` input alias into the existing `theme` list
- manual look-through component validation
- sector exposure
- industry exposure
- region exposure
- country-of-risk exposure
- issuer normalization across ADR / GDS / local-listing style holdings
- instrument-type exposure
- supplied fake FX and base-currency market value exposure
- leverage-adjusted gross exposure
- manual look-through exposure
- fallback when look-through is unavailable
- empty portfolio behavior
- missing optional metadata behavior
- deterministic ordering for exposure dictionaries

## Validation

Commands run:

```powershell
python -m py_compile .\ai_pm_agent.py
python -m py_compile .\src\ai_pm_agent\portfolio\models.py .\src\ai_pm_agent\portfolio\exposure.py .\src\ai_pm_agent\portfolio\__init__.py
python -m pytest -q tests\test_portfolio_exposure.py tests\test_portfolio_models.py
python -m pytest -q
```

Results:

- `ai_pm_agent.py` compile: passed
- portfolio module compile: passed
- targeted portfolio tests: `31 passed, 2 subtests passed`
- full pytest: `108 passed, 2 subtests passed`

## Safety Boundaries

- No PM decision logic changed.
- No recommendation logic changed.
- No portfolio-aware PM recommendations were added.
- No live API workflows were run.
- No OpenRouter, DeepSeek, LLM, web search, yfinance, broker sync, or external data provider workflows were run.
- No secrets were inspected.
- No dashboard, scheduler, FastAPI, advisor copilot, quant integration, or live research feature was added.
- Manual look-through is local fixture/manual metadata only.

## Known Limitations

- FX normalization depends on supplied local values and supplied fake or approved FX inputs.
- Manual look-through weights are not automatically fetched or refreshed.
- Sector, region, and country labels are free-form strings rather than controlled enums.
- Exposure summaries are informational only and should not be treated as trading, suitability, client, or investment advice.

## Recommended Next Step

Review this branch locally. If accepted, push and open a draft PR for Phase 3B review. Do not merge portfolio metadata into PM recommendation logic yet.
