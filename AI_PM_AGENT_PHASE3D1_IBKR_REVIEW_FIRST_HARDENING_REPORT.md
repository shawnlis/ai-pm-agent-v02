# AI PM Agent Phase 3D.1 IBKR Review-First Hardening Report

## Summary

This patch hardens the offline IBKR statement import adapter so imported rows are clearly staged, unverified, and review-required before any downstream portfolio exposure use.

The change addresses a GPT Pro audit concern that `portfolio_runner_ready_holdings.csv` could be misunderstood as verified holdings. The primary candidate output is now `staged_unverified_holdings.csv`; the old filename is emitted only as deprecated compatibility output for one version.

No live IBKR, broker API, credential handling, PDF parsing, PM recommendation wiring, or portfolio-aware PM decision behavior was added.

## Files Changed

- `src/ai_pm_agent/portfolio/ibkr_import.py`
- `tests/test_ibkr_import.py`
- `docs/IBKR_STATEMENT_IMPORT.md`

## Output Files Changed

Primary outputs now include:

- `parsed_holdings_review.csv`
- `staged_unverified_holdings.csv`
- `ibkr_import_warnings.md`
- `ibkr_import_summary.json`
- `ibkr_review_manifest.json`

Compatibility output:

- `portfolio_runner_ready_holdings.csv`

The compatibility CSV contains the same review-required rows as `staged_unverified_holdings.csv`, but it is documented as deprecated and unverified.

## Review Manifest

The new `ibkr_review_manifest.json` includes:

- `source_file`
- `source_file_sha256`
- `source_files`
- `generated_at`
- `offline_only`
- `review_required`
- `verified`
- `total_rows_seen`
- `parsed_review_rows`
- `candidate_rows`
- `excluded_rows`
- `warning_count`
- `blocking_issue_count`
- `warnings_by_code`
- `excluded_by_reason`
- `base_currency`
- `output_files`
- human-review notes

The manifest is intended as the machine-readable review gate for any later offline exposure run.

## Warning Codes

The review CSV now includes `warning_codes`. Current codes include:

- `MISSING_CURRENCY`
- `MISSING_MARKET_VALUE`
- `MISSING_TICKER`
- `MISSING_QUANTITY`
- `INVALID_QUANTITY`
- `CASH_LIKE_ROW_EXCLUDED`
- `UNKNOWN_INSTRUMENT_TYPE`
- `UNSUPPORTED_INSTRUMENT_TYPE`
- `NEGATIVE_QUANTITY`
- `NON_BASE_CURRENCY_MISSING_FX`
- `MANUAL_REVIEW_REQUIRED`
- `IBKR_IMPORT_REVIEW_REQUIRED`

Existing human-readable warning strings remain available in the review CSV, warnings Markdown, and summary JSON.

## Quarantine Rules

Rows remain visible in `parsed_holdings_review.csv`, warnings Markdown, summary JSON, and manifest, but are excluded from staged candidate holdings when they have:

- missing currency
- missing market value
- cash-like asset type
- negative quantity / short position
- unknown instrument type
- unsupported options, futures, warrants, CFDs, bonds/notes, or fund rows
- non-base currency without supplied base value or FX
- missing ticker
- missing or invalid quantity

Candidate rows still include `IBKR_IMPORT_REVIEW_REQUIRED` in the Phase 3C `notes` field.

## Tests Added Or Updated

`tests/test_ibkr_import.py` now covers:

- new primary `staged_unverified_holdings.csv` output
- deprecated compatibility output preservation
- valid manifest JSON creation
- manifest `review_required=true` and `verified=false`
- source file SHA-256 hash presence
- missing currency exclusion from candidate output
- non-base currency missing base value / FX exclusion
- missing market value exclusion
- negative quantity / short-position exclusion
- unknown instrument type exclusion
- unsupported option row exclusion
- candidate rows retaining `IBKR_IMPORT_REVIEW_REQUIRED`
- CLI `--statement` alias still working
- sample import compatibility with Phase 3C runner after review

## Validation Results

Commands run:

```powershell
python -m py_compile .\ai_pm_agent.py
python -m py_compile .\src\ai_pm_agent\portfolio\models.py .\src\ai_pm_agent\portfolio\exposure.py .\src\ai_pm_agent\portfolio\fixtures.py .\src\ai_pm_agent\portfolio\runner.py .\src\ai_pm_agent\portfolio\ibkr_import.py .\src\ai_pm_agent\portfolio\__init__.py
python -m py_compile .\scripts\portfolio_exposure_report.py
python -m py_compile .\scripts\ibkr_statement_import.py
python -m pytest -q tests\test_portfolio_recommendation_boundary.py
python -m pytest -q tests\test_portfolio_exposure.py tests\test_portfolio_models.py
python -m pytest -q tests\test_portfolio_runner.py
python -m pytest -q tests\test_ibkr_import.py
python -m pytest -q
```

Results:

- boundary tests: `2 passed, 1 warning`
- portfolio exposure/model tests: `31 passed, 2 subtests passed`
- portfolio runner tests: `11 passed`
- IBKR import tests: `10 passed`
- full pytest: `131 passed, 1 warning, 2 subtests passed`

Sample import commands:

```powershell
python .\scripts\ibkr_statement_import.py --statement .\examples\portfolio\ibkr_statement_sample.csv --out-dir .\reports\ibkr_import
python .\scripts\ibkr_statement_import.py --statement .\examples\portfolio\ibkr_flex_sectioned_sample.csv --out-dir .\reports\ibkr_import_flex
```

Sample results:

- simple sample: 4 review rows, 3 staged candidate rows, 1 excluded cash-like row, manifest created
- Flex-style sample: 3 review rows, 3 staged candidate rows, 0 excluded rows, manifest created

Generated reports remained under ignored `reports/`.

## Safety Boundaries

Confirmed:

- no secrets or broker credentials inspected
- no live IBKR workflow run
- no broker API used
- no live LLM/API/web/yfinance/OpenRouter/DeepSeek workflow run
- no PDF parser added
- no PM recommendation logic changed
- no portfolio data wired into PM decisions or PM prompts
- no dashboard, scheduler, FastAPI, advisor, quant, trading, or sizing feature added

## Remaining Limitations

- CSV/Flex-style local files only; PDF parsing remains out of scope.
- Candidate rows are still unverified and require manual review.
- Taxonomy, issuer canonical IDs, country/region/sector/theme enrichment, cash handling, and FX confirmation remain user-supplied review tasks.
- The deprecated compatibility output should be removed in a future version after downstream references migrate to `staged_unverified_holdings.csv`.

## Recommended Next Action

Open a draft PR for review-first hardening, review the new manifest/quarantine semantics, and do not start PDF parsing or live broker integration until the offline review gate is accepted.
