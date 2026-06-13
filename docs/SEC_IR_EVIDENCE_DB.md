# SEC / IR Evidence Database

## Purpose

The SEC / IR Evidence Database stores source-backed company evidence for gap monitors and future reviewed evidence packs. It is a source ledger, not a conclusion engine.

## Fixture-First MVP

The MVP imports only local SEC-shaped JSON fixtures. It does not call live SEC endpoints, use web search, read market data providers, call LLMs, inspect broker/account files, or use portfolio/client data.

Default local output path:

`reports/sec_ir_evidence_db/fixture_mvp/`

Output contracts:

- `evidence_db.sqlite`
- `company_evidence_ledger.csv`
- `metric_history.csv`
- `source_manifest.json`
- `ingestion_warnings.md`
- `SEC_IR_EVIDENCE_DB_FIXTURE_MVP_REPORT.md`

## Future Level 1 EDGAR Plan

Future implementation can add public read-only SEC EDGAR `data.sec.gov` sources after review. That should remain Level 1: no credentials, no account access, no broker access, no trading, no portfolio-aware recommendation path.

Planned first live endpoints:

- `https://data.sec.gov/submissions/CIK##########.json`
- `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`

Live implementation must add a user-agent placeholder, polite rate limiting, local cache controls, fail-closed retry behavior, and fixture parity tests before use.

## Source Confidence Rules

- Local SEC-shaped fixtures are tagged `high_fixture_official_shape`.
- Fixture confidence means the file follows an official endpoint shape; it does not mean live data was fetched.
- Every exported source captures path, SHA-256 hash, source date, capture date, confidence, and `fixture_only`.
- Missing or unsupported fields must produce structured warnings instead of silent conclusions.

## Boundaries

- No buy/sell/hold recommendations.
- No position sizing or portfolio-aware PM recommendations.
- No direct PM prompt wiring.
- No portfolio, IBKR, broker, account, client, API-key, token, `.env`, or `Openrouter.txt` data.
- Evidence can feed source ledgers and gap monitors.
- Evidence can enter PM workflows only through a separate reviewed evidence-pack interface.
