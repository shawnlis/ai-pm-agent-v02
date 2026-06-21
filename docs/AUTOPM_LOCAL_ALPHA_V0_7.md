# AUTOPM Local Alpha v0.7

`v0.7-autopm-local-alpha` is the first local-only autopm baseline after the
dual-mode split. It is intended for fixture-backed validation, auditability,
and operator review before any read-only live-provider work.

## Included

- dual-mode contract: `review_first` remains the default mode
- autopm schemas, policy defaults, data contracts, and Level 0 fixture providers
- capability acceptance coverage for the investment framework
- claim audit and output validation gates
- generic deterministic stock-picker ranking
- Asia AI Hardware ranking strategy and benchmark fixtures
- portfolio-aware recommendation and sizing logic
- rebalance proposal generation and local report writing
- explicit local CLI wrapper
- deterministic backtest harness
- paper portfolio simulation harness
- explicit-path local monitor and state-diff alert artifacts

## Not Included

- broker read
- broker execution
- real order placement
- scheduler
- notifications
- live SEC provider expansion for autopm
- live market data provider
- yfinance
- web search
- LLM or OpenRouter calls
- implicit scan of `reports/` or `outputs/`
- private portfolio, IBKR, account, broker, client, or credential files
- investment performance guarantees

## Operating Boundary

This release is local alpha only. It uses fixture or explicit local inputs and
writes artifacts only to explicit output directories. Proposal and paper outputs
must remain non-executed:

- rebalance proposal rows must include `not_executed=true`
- paper portfolio records must include `simulated=true`
- critical monitor alerts require manual review only

`autopm` output is not a broker order and does not create live trading behavior.

## Accuracy Boundary

The system can improve output hygiene, not guarantee investment correctness.
The release standard is:

- sources are explicit
- claims are auditable
- decisions are deterministic
- failures are detectable
- backtests and paper runs are reproducible

Backtests are not proof of future performance. Paper fills are simulated.
Fixture quality limits result quality.

## Next Phase

The recommended next phase is a read-only live-provider boundary PR. It should
remain disabled by default, fail closed in offline mode, record provider
metadata, and avoid broker/account access. Broker execution requires a separate
future adapter with explicit implementation, tests, configuration, and approval.
