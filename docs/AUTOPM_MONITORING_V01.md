# AUTOPM Monitoring V01

Autopm monitoring is local state-diff artifact generation only.

It compares two explicitly supplied autopm run states and writes review
artifacts:

- `AUTOPM_MONITOR_ALERTS.md`
- `autopm_alerts.csv`
- `autopm_monitor_state.json`
- `autopm_monitor_warnings.md`

## Boundaries

- no scheduler
- no notifications
- no Telegram, Slack, Email, or WhatsApp integration
- no implicit scan of `reports/` or `outputs/`
- no live SEC provider
- no live market data
- no yfinance
- no web or LLM calls
- no broker/account read
- no broker execution
- no order placement

All input paths must be explicit. Broker/client/account/IBKR-looking paths fail
closed before file contents are read.

## Alert Meaning

Alerts are review triggers, not trade instructions.

Critical alerts require manual review only. They do not trigger sell, trim,
order, broker, notification, or scheduler behavior.

## Alert Types

- `NEW_TOP_PICK`
- `REMOVED_TOP_PICK`
- `RANK_UPGRADE`
- `RANK_DOWNGRADE`
- `ACTION_UPGRADE`
- `ACTION_DOWNGRADE`
- `TARGET_WEIGHT_INCREASE`
- `TARGET_WEIGHT_DECREASE`
- `THESIS_KILL_TRIGGER_ACTIVE`
- `REQUIRED_EVIDENCE_MISSING`
- `EVIDENCE_STALE`
- `PRICE_OR_VALUATION_STALE`
- `CLAIM_AUDIT_FAILED`
- `OUTPUT_VALIDATION_INVALID`
- `POLICY_BREACH`
- `CONCENTRATION_BREACH`
- `CASH_CONSTRAINT`
- `PAPER_DRAWDOWN_ALERT`
- `TURNOVER_ALERT`

Paper/backtest alerts are not investment performance guarantees. Fixture
quality determines monitor output quality.
