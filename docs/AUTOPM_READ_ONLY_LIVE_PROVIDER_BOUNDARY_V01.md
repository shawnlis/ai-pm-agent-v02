# AUTOPM Read-Only Live Provider Boundary V01

PR13 defines a default-off read-only live data boundary for autopm. It does not
turn autopm into a live recommendation, broker, execution, scheduler, or
notification system.

## Purpose

The boundary lets future PRs add official/public or licensed market data reads
without weakening the `v0.7-autopm-local-alpha` safety contract. It defines
permission checks, provider metadata, and transport injection before any live
data can be used by ranking, recommendation, rebalance, backtest, paper, or
monitor flows.

## Allowed Future Source Types

- public official read-only sources
- licensed market/fundamental data vendor read-only sources

Supported PR13 levels:

- `LEVEL_1_PUBLIC_OFFICIAL_READ_ONLY`
- `LEVEL_2_MARKET_DATA_VENDOR_READ_ONLY`

## Forbidden Source Types

- broker account data
- execution endpoints
- private account files
- client data
- IBKR, moomoo, Webull, bank, custodian, account, statement, or
  `portfolio.csv` paths
- implicit scans of `reports/` or `outputs/`
- LLM, web-search, or yfinance workflows

## Default-Off Contract

Live provider requests fail closed unless all of the following are explicit:

- `allow_live_fetch=true`
- `offline=false`
- provider name
- read-only provider level
- allowlisted domain
- `https` URL
- read-only `GET` or `HEAD` method
- user agent when required
- safe cache directory when caching is enabled

`POST`, `PUT`, `PATCH`, and `DELETE` are forbidden. Non-allowlisted domains are
forbidden. Broker/account/client-looking URLs or paths are forbidden.

## Provider Result Manifest

Every provider result manifest includes:

- `provider_name`
- `provider_level`
- `retrieval_time`
- `as_of_date`
- `source_url`
- `source_hash`
- `cache_path` if caching is used
- `stale`
- `warning_codes`
- `read_only=true`
- `not_broker_data=true`
- `not_execution_capable=true`

## Transport Boundary

The provider shell uses dependency-injected transport. Tests use fake transports
and make no network calls. The default transport refuses network access and
raises until a future PR implements a reviewed transport.

## Non-Integration Boundary

PR13 does not integrate live providers into:

- ranking
- recommendations
- sizing
- rebalance
- output validation
- backtest
- paper portfolio
- monitor
- CLI live mode

Future integration must be a separate PR with tests showing offline mode blocks
live reads and that source manifests preserve provenance.

## Accuracy Boundary

Read-only provider access does not prove prediction accuracy, investment
performance, or trading readiness. It only makes source retrieval more
auditable. Claim audit, output validation, backtest, paper simulation, and
manual review gates still apply.
