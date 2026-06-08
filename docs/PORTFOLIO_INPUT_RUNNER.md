# Offline Portfolio Input Runner

The Phase 3C portfolio input runner turns local static CSV or JSON files into an informational portfolio exposure report.

It is local/offline only. It does not connect to brokers, fetch live prices, fetch live FX rates, fetch ETF/fund/crypto constituents, call LLMs, call OpenRouter/DeepSeek, run web search, or change PM recommendations.

## Command

From the repository root:

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

## Input Files

All inputs are local CSV or JSON files. JSON files may be a list of row objects or an object with a `rows` list.

### Holdings

Suggested sample: `examples/portfolio/holdings_sample.csv`

Required columns:

- `portfolio_id`
- `as_of_date`
- `ticker`
- `quantity`

Supported columns:

- `portfolio_id`
- `as_of_date`
- `ticker`
- `name`
- `quantity`
- `market_value_local`
- `trading_currency`
- `base_currency`
- `fx_rate_to_base`
- `market_value_base`
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
- `themes`
- `leverage_factor`
- `notes`

### Issuer Mapping

Suggested sample: `examples/portfolio/issuer_mapping_sample.csv`

Columns:

- `ticker`
- `issuer_name`
- `issuer_canonical_id`
- `underlying_issuer_name`
- `underlying_ticker`
- `listing_country`
- `country_of_risk`
- `region`

### Taxonomy Mapping

Suggested sample: `examples/portfolio/taxonomy_mapping_sample.csv`

Columns:

- `ticker`
- `sector`
- `industry`
- `region`
- `country_of_risk`
- `themes`

### Manual Look-Through

Suggested sample: `examples/portfolio/manual_lookthrough_sample.csv`

Columns:

- `parent_ticker`
- `component_issuer_name`
- `component_issuer_canonical_id`
- `component_ticker`
- `component_weight`
- `sector`
- `industry`
- `country_of_risk`
- `region`
- `themes`
- `source_note`

Manual look-through is not fetched. If component weights do not sum to 100% for a parent holding, the runner emits a warning. Residual exposure is not inferred unless a residual component is supplied.

### FX Snapshot

Suggested sample: `examples/portfolio/fx_snapshot_sample.csv`

Columns:

- `currency`
- `base_currency`
- `fx_rate_to_base`
- `as_of_date`
- `source_note`

FX values are user-supplied static inputs. The runner does not verify them against live markets.

## Behavior

The runner:

- reads local files only
- validates required holdings columns
- validates numeric values
- builds a `PortfolioSnapshot`
- fills missing issuer/taxonomy fields from optional mappings when supplied
- fills missing FX rates from the optional FX snapshot when supplied
- produces Markdown and optional JSON output
- handles missing optional input files by warning and continuing
- keeps line-item exposure and manual look-through exposure separate

The runner emits warnings for:

- missing optional files that were explicitly requested
- missing issuer mapping
- missing taxonomy metadata
- missing FX rates for non-base-currency holdings
- missing base/local values
- manual look-through weights that do not sum to 100%
- mixed portfolio IDs or as-of dates in the holdings file

## Report Output

The Markdown report includes:

- run metadata
- input files used
- validation warnings
- line-item holdings
- sector exposure
- industry exposure
- region exposure
- country-of-risk exposure
- issuer exposure
- instrument-type exposure
- theme exposure
- currency exposure
- base-market-value exposure
- leverage-adjusted gross exposure
- concentration summary
- manual look-through exposure
- limitations

The JSON summary includes:

- `portfolio_id`
- `as_of_date`
- `base_currency`
- `counts`
- `warnings`
- `input_files`
- `exposures`
- `leverage_adjusted_gross_exposure`
- `concentration`
- `lookthrough_summary`

## Limitations

All exposure results depend on user-supplied/static inputs.

This runner does not:

- connect to brokers
- fetch live market data
- fetch live FX rates
- fetch ETF/fund/crypto constituents
- normalize taxonomy values to GICS, BICS, ISO, MSCI, broker, or provider standards
- handle multi-currency cash balances
- change PM recommendations, ratings, actions, or research execution

Exposure output is informational only and is not investment advice, trading advice, suitability advice, VaR, margin analysis, stress loss, or a risk model.
