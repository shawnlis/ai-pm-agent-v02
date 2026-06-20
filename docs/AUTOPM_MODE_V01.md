# Autopm Mode v0.1 Policy

## Purpose

This document defines the policy contract for evolving AI PM Agent from a
review-first-only system into a dual-mode public-company research and portfolio
decision system.

This is documentation and policy only. It does not add a recommendation engine,
portfolio-aware PM wiring, broker integration, order generation, or live
execution behavior.

## Mode Values

### `review_first`

`review_first` is the default mode.

It supports:

- evidence organization
- SEC/IR source ledgers
- thesis-gap monitoring
- research queue generation
- risk reporting
- approval packets
- manual review handoffs

Default-mode outputs must not include:

- buy
- sell
- hold
- add
- trim
- target position
- target_weight_pct
- position size
- rebalance
- order
- trade instruction
- broker execution

Existing review-first modules must keep this behavior unless a dedicated
migration PR changes them with explicit tests.

### `autopm`

`autopm` is an explicit opt-in mode.

Autopm may output PM recommendations only when explicitly enabled by command,
config, or test fixture. Autopm must not be inferred from the presence of
portfolio files, risk reports, market data, generated reports, cached data, or
prior PM decisions.

Allowed autopm outputs:

- `rating`
- `action`
- stock picker rankings
- universe rankings
- `target_weight_pct`
- `current_weight_pct`
- `delta_weight_pct`
- `max_position_pct`
- `conviction_score`
- `risk_budget_used`
- `rebalance_reason_codes`
- `order_intent` in proposal or paper form only
- `thesis_kill_triggers`
- `next_review_date`
- rebalance proposals

Autopm outputs are not broker orders. Broker execution is not enabled unless a
future explicit execution adapter is implemented, tested, configured, and
separately enabled.

## Required Config Flags

Default configuration:

```text
AUTOPM_MODE=disabled
AUTOPM_ALLOW_PORTFOLIO_CONTEXT=false
AUTOPM_ALLOW_LIVE_MARKET_DATA=false
AUTOPM_ALLOW_BROKER_READ=false
AUTOPM_ALLOW_EXECUTION=false
```

Allowed values:

```text
AUTOPM_MODE=disabled|paper|proposal|live_recommendation
AUTOPM_ALLOW_PORTFOLIO_CONTEXT=false|true
AUTOPM_ALLOW_LIVE_MARKET_DATA=false|true
AUTOPM_ALLOW_BROKER_READ=false|true
AUTOPM_ALLOW_EXECUTION=false|true
```

Interpretation:

- `AUTOPM_MODE=disabled`: default review-first behavior. No autopm
  recommendation outputs.
- `AUTOPM_MODE=proposal`: may produce PM proposals and rebalance proposals for
  human review.
- `AUTOPM_MODE=paper`: may produce paper records, never real broker orders.
- `AUTOPM_MODE=live_recommendation`: may produce recommendation artifacts, but
  still does not imply broker execution.
- `AUTOPM_ALLOW_PORTFOLIO_CONTEXT=true`: portfolio context may be used only
  inside explicit autopm workflows.
- `AUTOPM_ALLOW_LIVE_MARKET_DATA=true`: live market data may be used only
  through explicit provider contracts with stale/reliability metadata.
- `AUTOPM_ALLOW_BROKER_READ=true`: broker/account read imports may be used only
  through explicit read-only adapters.
- `AUTOPM_ALLOW_EXECUTION=true`: reserved for future execution work and must
  remain inert until a broker execution adapter exists.

## Escalation Path

Autopm capability must advance in this order:

1. Fixture source packs
2. Proposal output
3. Paper portfolio records
4. Live recommendation artifacts
5. Future execution adapter, only if separately implemented, tested,
   configured, reviewed, and enabled

No stage may silently imply the next stage. In particular, `live_recommendation`
does not permit live broker execution.

## Execution Boundary

No current autopm policy permits real broker orders.

Real execution requires a future dedicated PR that adds:

- explicit broker execution adapter
- dry-run default
- test coverage for forbidden side effects
- explicit config gates
- human approval gates
- idempotent logs
- rollback/removal instructions
- no secrets in code, tests, docs, logs, or PR bodies

Until that future adapter exists, all execution-related outputs must remain
proposals or paper records.

## Required Autopm Gates

Future autopm recommendations must pass these gates before emitting
recommendation artifacts:

1. Evidence gate
   - Primary or official evidence preferred
   - Weak or stale evidence caps conviction
   - Missing evidence cannot be inferred

2. Claim-audit gate
   - Recommendation claims must trace to source evidence or policy rules
   - Reason codes must be reproducible
   - Unsupported high-conviction claims must fail closed

3. Data-quality gate
   - Stale, missing, or low-reliability market data blocks valuation-dependent
     recommendations
   - Provider output must include source and reliability metadata

4. Valuation gate
   - Recommendations must state valuation basis
   - Reverse valuation or downside scenario required for high-conviction names

5. Portfolio gate
   - Max single-name exposure
   - Max theme exposure
   - Max country/region exposure
   - Leverage-adjusted exposure
   - Cash and liquidity constraints
   - Concentration and correlation warnings

6. Risk gate
   - Drawdown risk
   - Liquidity risk
   - Earnings/catalyst risk
   - Working-capital red flags
   - Client/account data must not be used unless explicitly part of a local
     personal portfolio file for that run

7. Red-team gate
   - Strongest bear case
   - Missing evidence
   - Thesis breaker
   - What would force downgrade
   - What would force sell or trim

8. Output-validation gate
   - Run manifest required
   - Source manifest required
   - Policy manifest required
   - Claim audit must pass in strict mode for valid output
   - Target weights must respect policy caps
   - Output mode must be explicit

## Review-First Modules

These modules remain review-first unless a dedicated migration PR changes them:

- `src/ai_pm_agent/evidence_db/`
- `src/ai_pm_agent/thesis_gap_monitor/`
- `src/ai_pm_agent/opportunity_discovery/`
- `src/ai_pm_agent/ai_infra_pipeline/`
- `src/ai_pm_agent/portfolio_risk_cockpit/`
- `src/ai_pm_agent/short_put_risk_monitor/`
- `src/ai_pm_agent/risk_cockpit_pipeline/`
- `src/ai_pm_agent/approval/`

They must not emit default-mode buy/sell/hold/sizing/rebalance/order/trade
instructions.

## Provider Rules

Any provider above Level 0 must require explicit config and tests.

Provider levels:

- Level 0: fixtures only
- Level 1: public read-only official APIs
- Level 2: market/fundamental data providers
- Level 3: broker/account read-only import
- Level 4: paper trading
- Level 5: live execution

No provider may silently fall back to fabricated data.

All provider outputs should include:

- `provider_name`
- `provider_level`
- `retrieval_time`
- `source_url` or `source_id` when available
- stale flag
- confidence or reliability
- `warning_codes`

## Test Requirements

Policy tests must confirm:

- `review_first` remains the default.
- autopm must be explicit.
- broker execution remains disabled by default.
- docs do not describe default-mode recommendation, sizing, rebalance, order,
  or trade outputs.
