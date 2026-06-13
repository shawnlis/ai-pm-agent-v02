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

## Level 1 SEC EDGAR Live Fetch Mode

Level 1 live fetch mode is available only when explicitly requested with `--live-sec-fetch`. Fixture mode remains the default.

Live mode uses public, no-secret, read-only SEC JSON endpoints only:

- `https://www.sec.gov/files/company_tickers.json`
- `https://data.sec.gov/submissions/CIK##########.json`
- `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`

Required live-mode flags:

- `--live-sec-fetch`
- `--sec-user-agent "<Name email@example.com>"`

Optional live-mode flags:

- `--cik <CIK>` to avoid ticker-resolution fetch.
- `--sec-cache-dir <path>` to override the default cache directory.
- `--force-refresh` to bypass valid cache files.

`--offline` blocks live network access. Live mode cannot be combined with fixture files; run either fixture mode or live mode.

Default live cache path:

`reports/sec_ir_evidence_db/sec_cache/`

Cache files:

- `company_tickers.json`
- `submissions_CIK.json`
- `companyfacts_CIK.json`
- matching `*.meta.json` metadata sidecars

Cache metadata records source URL, retrieval time, SHA-256 hash, API level, source type, HTTP status, and a User-Agent hash. It does not store secrets or credentials.

Live mode fails closed. HTTP errors, invalid JSON, missing User-Agent, and CIK resolution failures emit structured warnings and do not fabricate evidence or metrics. The adapter uses cache-first behavior and does not retry aggressively.

## Source Confidence Rules

- Local SEC-shaped fixtures are tagged `high_fixture_official_shape`.
- Fixture confidence means the file follows an official endpoint shape; it does not mean live data was fetched.
- Public SEC EDGAR live sources are tagged `high_official_sec_edgar_public_api`.
- Every exported source captures path, SHA-256 hash, source date, capture date, confidence, and `fixture_only`.
- Live source manifests also capture source URL, cache path, retrieval timestamp, cache hit/miss, Level 1 API flags, and warning codes.
- Missing or unsupported fields must produce structured warnings instead of silent conclusions.

## Boundaries

- No buy/sell/hold recommendations.
- No position sizing or portfolio-aware PM recommendations.
- No direct PM prompt wiring.
- No portfolio, IBKR, broker, account, client, API-key, token, `.env`, or `Openrouter.txt` data.
- No live source is allowed unless `--live-sec-fetch` and `--sec-user-agent` are both supplied.
- Evidence can feed source ledgers and gap monitors.
- Evidence can enter PM workflows only through a separate reviewed evidence-pack interface.
