# Risk Cockpit Pipeline v0.5.2

Risk Cockpit Pipeline v0.5.2 is a local/offline risk review pipeline. It combines Portfolio Risk Cockpit v0.5.0 outputs, Short Put Risk Monitor v0.5.1 outputs, and fixture-only market data into a consolidated handoff.

This is a risk review pipeline, not an investment recommendation.

## Purpose

The pipeline creates a review layer across portfolio exposure artifacts and short put exposure artifacts. It is intended to make missing, stale, mismatched, or review-risk inputs visible before any human uses the underlying reports.

It does not create buy, sell, hold, roll, close, open, assignment, exercise, hedge, sizing, suitability, or client advice.

## Architecture

- Existing artifact mode reads previously generated Portfolio Risk Cockpit and Short Put Risk Monitor report directories.
- Foundation report mode runs the existing offline fixture runners first, then reads their generated outputs.
- Fixture market data is loaded through a provider abstraction that is Level 0, local-only, and network-free.
- Enrichment compares fixture market data against source risk artifacts for review context only.

## Input Contracts

Existing artifact mode:

```powershell
python .\scripts\risk_cockpit_pipeline.py `
  --portfolio-report-dir .\reports\portfolio_risk_cockpit\v050\20260613 `
  --short-put-report-dir .\reports\short_put_risk_monitor\v051\20260613 `
  --market-data-fixture .\tests\fixtures\risk_cockpit_pipeline\fixture_market_data_v052.csv `
  --out-dir .\reports\risk_cockpit_pipeline\v052\20260613 `
  --offline
```

Foundation report mode:

```powershell
python .\scripts\risk_cockpit_pipeline.py `
  --portfolio-input .\tests\fixtures\portfolio_risk_cockpit\sample_portfolio_v050.csv `
  --short-put-input .\tests\fixtures\short_put_risk_monitor\sample_short_puts_v051.csv `
  --market-data-fixture .\tests\fixtures\risk_cockpit_pipeline\fixture_market_data_v052.csv `
  --out-dir .\reports\risk_cockpit_pipeline\v052\20260613 `
  --run-foundation-reports `
  --as-of-date 2026-06-13 `
  --offline
```

The path guard rejects real-data-looking input paths before file reads, including `portfolio.csv`, `IBKR Positions/`, and paths containing `ibkr`, `broker`, or `client`.

## Output Contracts

The pipeline writes:

- `RISK_COCKPIT_PIPELINE_V052.md`
- `risk_cockpit_pipeline_index.json`
- `risk_artifact_summary.csv`
- `risk_warning_summary.csv`
- `market_data_snapshot.csv`
- `risk_enrichment_summary.csv`
- `risk_cockpit_pipeline_warnings.md`

Default outputs are under ignored `reports/risk_cockpit_pipeline/v052/<YYYYMMDD>/`.

## Market Data Provider Abstraction

This PR implements only `fixture_market_data`.

- `provider_name`: `fixture_market_data`
- `provider_level`: `Level 0`
- `network_access`: `false`
- `live_market_data`: `false`
- `fixture_only`: `true`

The abstraction prepares for later Level 2 read-only market data API integration, but no HTTP/API provider exists in v0.5.2.

## Fixture-Only Market Data Behavior

Fixture market data is review context only. It does not overwrite Portfolio Risk Cockpit market values and does not overwrite Short Put Risk Monitor current underlying prices.

The pipeline emits review warnings for missing market data, stale market data, and material price mismatches. Missing or stale market data does not create fabricated values.

Every market data fixture row must explicitly declare `fixture_only=true`. Accepted true values are `true`, `1`, `yes`, and `y`. Empty values, false values, or unrecognized values fail closed with `MARKET_DATA_NOT_FIXTURE`.

Any non-fixture market data row fails closed. The provider remains Level 0, network-free, non-live, and fixture-only; the pipeline does not silently coerce non-fixture data into fixture data.

## Warning Definitions

- `MISSING_PORTFOLIO_ARTIFACT`: a required portfolio artifact is absent.
- `MISSING_SHORT_PUT_ARTIFACT`: a required short put artifact is absent.
- `MISSING_MARKET_DATA`: no fixture market data exists for a ticker.
- `STALE_MARKET_DATA`: fixture market data is older than the configured maximum age.
- `PRICE_MISMATCH_NEEDS_REVIEW`: short put source price differs from fixture market data beyond the configured threshold.
- `MARKET_DATA_FIXTURE_ONLY`: market data came from a local fixture.
- `MARKET_DATA_NOT_FIXTURE`: market data row was not explicitly marked fixture-only.
- `RISK_ARTIFACT_NEEDS_REVIEW`: a source risk artifact contains review-risk rows or warning codes.
- `PIPELINE_REVIEW_REQUIRED`: at least one review-risk warning is present.
- `PIPELINE_FAILED_CLOSED`: pipeline failed closed and wrote an audit index.
- `MARKET_DATA_LOAD_FAILED`: market data fixture loading failed.
- `FOUNDATION_REPORT_FAILED`: foundation report generation failed.
- `ARTIFACT_READ_FAILED`: source artifact parsing failed.
- `DISALLOWED_REAL_DATA_PATH`: a real-data-looking path was rejected before file read.
- `NO_LIVE_MARKET_DATA`: no live market data provider was used.

## Fail-Closed Audit Behavior

If execution fails after the pipeline has started, the pipeline writes `risk_cockpit_pipeline_index.json` with failed statuses, warning codes, `error_message`, and the normal safe boundary fields.

Failure indexes are audit artifacts, not recommendations. They are written so the operator can see what had already run, which step failed, and why the output must not be treated as complete.

Malformed artifacts, non-fixture market data, missing data, stale market data, and mismatched market data must not be treated as usable without manual review.

## Safety Boundaries

- Local/offline risk review only.
- Fixture market data only.
- No live market data.
- No broker connection.
- No IBKR content inspection.
- No trading or order placement.
- No yfinance.
- No web search.
- No LLM/OpenRouter/DeepSeek.
- No client data.
- No PM prompt or recommendation wiring.
- No buy/sell/hold/roll/close/open/assignment/exercise/hedge/sizing recommendation.

## Known Limitations

- Market data is fixture-only and may be stale by design.
- Stress, exposure, and option risk outputs remain simple risk indicators from their source reports.
- The pipeline does not model payoff curves, margin, greeks, volatility, assignment probability, suitability, taxes, liquidity, slippage, or client constraints.

## Why This Is Not Advice

The pipeline consolidates source artifacts and flags review gaps. It does not decide what to buy, sell, hold, roll, close, open, assign, exercise, hedge, or size. Positive estimated P/L remains review context only and is not an opportunity signal.
