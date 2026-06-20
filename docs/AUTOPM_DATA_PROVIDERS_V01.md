# Autopm Data Providers v0.1

## Purpose

This document defines the PR2 autopm provider foundation. It covers schema,
policy, data contracts, and Level 0 fixture providers only.

This PR does not add stock picking, PM recommendations, sizing, rebalance
logic, CLI workflows, live SEC providers, broker reads, broker execution, or
generated reports.

## Provider Levels

Provider levels are explicit:

- `LEVEL_0_FIXTURE`: local deterministic fixtures only
- `LEVEL_1_PUBLIC_OFFICIAL`: future read-only official public APIs
- `LEVEL_2_MARKET_DATA_VENDOR`: future read-only market/fundamental providers
- `LEVEL_3_BROKER_READ_ONLY`: future broker/account read-only import
- `LEVEL_4_PAPER_TRADING`: future paper trading records
- `LEVEL_5_LIVE_EXECUTION`: reserved for future execution work

Only `LEVEL_0_FIXTURE` is implemented in this PR.

## Default Mode

Autopm remains disabled by default:

```text
AutopmMode.DISABLED
```

Provider classes do not enable autopm mode, generate recommendations, or
produce order instructions.

## Snapshot Metadata

Every provider snapshot must include:

- `ticker`
- `provider_name`
- `provider_level`
- `retrieval_time`
- `as_of_date`
- `source_ids`
- `reliability`
- `stale`
- `warning_codes`
- `fixture_only`

The PR2 contracts define:

- `MarketSnapshot`
- `FundamentalSnapshot`
- `EstimateSnapshot`
- `TechnicalSnapshot`
- `NewsCatalystSnapshot`
- `EvidenceSnapshot`
- `PortfolioInputSnapshot`

## Fixture Providers

Implemented fixture providers:

- `FixtureMarketDataProvider`
- `FixtureFundamentalDataProvider`
- `FixtureEstimateDataProvider`

They read only explicit local `.csv` or `.json` fixture files.

Fixture providers fail closed when:

- the file is missing
- the file type is not `.csv` or `.json`
- required columns are missing
- `fixture_only` is not true
- `provider_level` is supplied and is not `LEVEL_0_FIXTURE`
- `source_ids` is empty
- numeric fields cannot be parsed
- `as_of_date` is not `YYYY-MM-DD`

Stale fixture data is marked with `stale=True` and warning code `STALE_DATA`.

## Boundaries

Fixture providers must not:

- make network calls
- call yfinance
- call LLMs
- inspect `.env`, `Openrouter.txt`, credentials, tokens, or browser sessions
- inspect private portfolio exports
- inspect `IBKR Positions/`
- import broker modules
- place orders
- emit buy/sell/hold/add/trim recommendations

Review-first modules must not import `ai_pm_agent.autopm`.

## Validation

Required PR2 validation:

```powershell
python -m py_compile src/ai_pm_agent/autopm/models.py src/ai_pm_agent/autopm/policy.py src/ai_pm_agent/autopm/data_contracts.py src/ai_pm_agent/autopm/providers.py
python -m pytest -q tests/test_autopm_models.py tests/test_autopm_policy.py tests/test_autopm_providers.py
python -m pytest -q
```
