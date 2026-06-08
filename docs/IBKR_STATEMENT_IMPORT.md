# Offline IBKR Statement Import Adapter

The Phase 3D IBKR statement import adapter converts local IBKR-exported CSV or Flex-style CSV rows into the Phase 3C portfolio input format.

It is local/offline only. It does not connect to IBKR, use broker APIs, inspect credentials, fetch live prices, fetch live FX, call LLMs, run web search, or change PM recommendations.

## Command

From the repository root:

```powershell
python .\scripts\ibkr_statement_import.py `
  --statement examples\portfolio\ibkr_statement_sample.csv `
  --out-dir reports\ibkr_import
```

The `reports/` directory is ignored by Git.

Use repeated `--statement` arguments for multiple files. `--input` is accepted as an alias. If `--portfolio-id` is omitted, the adapter writes `ibkr_import_review`.

## Outputs

The adapter writes four local review artifacts:

- `parsed_holdings_review.csv`
- `portfolio_runner_ready_holdings.csv`
- `ibkr_import_warnings.md`
- `ibkr_import_summary.json`

`portfolio_runner_ready_holdings.csv` uses the Phase 3C holdings columns, but it is not a verification certificate. Rows remain review-required until a human checks the review CSV and warnings file against the original statement.

## Supported Local Inputs

Supported:

- plain CSV exports with a single header row
- sectioned Flex-style CSV rows shaped like `Section,Header,...` and `Section,Data,...`
- Open Positions / Positions sections

Not supported yet:

- PDF statements
- XML parsing
- broker login/API sync
- trades, cash ledger, performance report, tax lot, or activity-section conversion
- live market price, live FX, or ETF constituent lookup

## Recognized Field Mapping

The adapter maps common IBKR-style fields into the Phase 3C schema:

| Phase 3C field | Recognized IBKR-style inputs |
| --- | --- |
| `ticker` | `Symbol`, `Ticker`, `Local Symbol`, `IBKR Symbol` |
| `name` | `Description`, `Name`, `Security Description` |
| `quantity` | `Quantity`, `Position`, `Qty`, `Shares`, `Ending Quantity` |
| `market_value_local` | `Market Value`, `Current Value`, `Ending Value`, `Value` |
| `market_value_base` | `Market Value in Base`, `Market Value Base`, `Base Market Value` |
| `trading_currency` | `Currency`, `CurrencyPrimary`, `Trading Currency` |
| `base_currency` | CLI `--base-currency` or statement base-currency fields |
| `instrument_type` | mapped from `Asset Category` / `Security Type` |
| `issuer_name` | `Issuer`, `Issuer Name` |
| `underlying_ticker` | `Underlying Symbol` |
| `listing_country` | `Listing Country`, `Country`, `Country of Listing` |
| `notes` | source file, row, section, asset category, security type, Conid, ISIN, exchange, and account metadata |

The adapter intentionally leaves issuer canonical IDs, sector, industry, region, country-of-risk, themes, and leverage factors blank unless a local statement field directly supplies a supported value. These should be reviewed or enriched manually before portfolio exposure reporting.

If a source row is missing a trading currency, the adapter defaults that row to the selected base currency only so the review files stay usable. This fallback is not verified currency data and must be checked against the original statement before exposure reporting.

## Warning Behavior

The adapter warns on:

- ambiguous values across equivalent fields
- missing or blank trading currency; these rows are defaulted to base currency for review convenience only
- missing ticker
- missing or invalid quantity
- missing market value
- non-base-currency rows without base value or FX rate
- unmapped asset/security type
- cash-like rows, which are excluded and require manual review

Rows that cannot become valid Phase 3C holdings are still included in `parsed_holdings_review.csv` with `parse_status=excluded`, but they are not written to `portfolio_runner_ready_holdings.csv`.

## Human Review Boundary

Imported holdings are unverified until reviewed.

Before using `portfolio_runner_ready_holdings.csv` in the Phase 3C exposure runner:

- confirm tickers, quantities, currencies, and market values against the original statement
- review any excluded rows
- handle cash and FX balances manually
- add or review issuer canonical IDs
- add or review sector, industry, region, country-of-risk, and themes
- confirm the as-of date and base currency
- treat any base-currency fallback for missing trading currency as unverified until manually corrected or confirmed

The adapter output is a local import-review artifact only. It is not investment advice, trading advice, suitability advice, tax advice, or a PM recommendation.

## Safety Boundaries

This adapter does not:

- connect to IBKR
- use broker APIs
- request credentials
- read `.env`, `Openrouter.txt`, API keys, tokens, or secret files
- run live LLM, web search, yfinance, OpenRouter, DeepSeek, or live API workflows
- fetch ETF/fund/crypto constituents
- parse PDF statements
- add trading, scheduling, dashboard, advisor, or PM recommendation behavior
