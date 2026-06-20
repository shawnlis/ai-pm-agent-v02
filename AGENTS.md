# AGENTS.md

## Project Mission

AI PM Agent is evolving into a dual-mode public-company research and
portfolio decision system.

The project has two modes:

1. `review_first`
   - Evidence organization
   - Gap monitoring
   - Research queue generation
   - Risk reporting
   - Approval packets
   - No buy/sell/hold/sizing/rebalance outputs

2. `autopm`
   - Explicit opt-in automatic PM mode
   - Stock picking
   - Universe ranking
   - Portfolio-aware PM recommendations
   - Target weights and position sizing
   - Rebalance proposal generation
   - Monitoring and paper/proposal adapters, when explicitly enabled

Default behavior must remain `review_first` unless a command, config, or
test explicitly enables `autopm`.

## Non-Negotiable Repository Rules

Do not inspect or commit:

- `.env`
- `Openrouter.txt`
- API keys
- tokens
- credentials
- browser sessions
- broker credentials
- private portfolio exports
- generated `outputs/`
- generated `reports/`
- SQLite databases
- local caches

Do not commit generated local artifacts unless they are tiny intentional test
fixtures under `tests/fixtures/` or `examples/`.

Every new module must have tests.

Every PR must include:

- scope summary
- commands run
- tests passed
- files changed
- known limitations
- safety/boundary notes

## Mode Boundaries

### `review_first` Modules

The following modules must remain review-first unless a dedicated migration PR
changes them:

- `src/ai_pm_agent/evidence_db/`
- `src/ai_pm_agent/thesis_gap_monitor/`
- `src/ai_pm_agent/opportunity_discovery/`
- `src/ai_pm_agent/ai_infra_pipeline/`
- `src/ai_pm_agent/portfolio_risk_cockpit/`
- `src/ai_pm_agent/short_put_risk_monitor/`
- `src/ai_pm_agent/risk_cockpit_pipeline/`
- `src/ai_pm_agent/approval/`

These modules must not output:

- buy
- sell
- hold
- add
- trim
- target position
- position size
- target weight
- rebalance
- order
- trade instruction

### `autopm` Modules

Autopm modules may output PM recommendations only when explicitly enabled.

Allowed autopm outputs include:

- stock picker rankings
- universe rankings
- rating
- action
- target_weight_pct
- current_weight_pct
- delta_weight_pct
- max_position_pct
- conviction_score
- risk_budget_used
- rebalance_reason_codes
- order_intent in paper/proposal form only
- thesis_kill_triggers
- next_review_date
- rebalance proposals

Autopm outputs are not broker orders.

Autopm modules must not place real broker orders unless a future broker
execution adapter is explicitly implemented, tested, configured, and enabled.
Until then, execution-related outputs are proposals or paper records only.

## Required Autopm Gates

Autopm recommendations must pass these gates:

1. Evidence gate
   - Primary or official evidence preferred
   - Weak or stale evidence caps conviction
   - Missing evidence cannot be inferred

2. Claim-audit gate
   - Recommendation claims must be traceable to source evidence or policy rules
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

## Data Provider Rules

Provider levels:

- Level 0: fixtures only
- Level 1: public read-only official APIs
- Level 2: market/fundamental data providers
- Level 3: broker/account read-only import
- Level 4: paper trading
- Level 5: live execution

Any provider above Level 0 must require explicit config and tests.

No provider may silently fall back to fabricated data.

All provider outputs must include:

- provider_name
- provider_level
- retrieval_time
- source_url or source_id when available
- stale flag
- confidence/reliability
- warning_codes

## Development Workflow

Preferred PR order:

1. Documentation/spec
2. Data models
3. Loader/provider interface
4. Deterministic logic
5. Report writer
6. CLI
7. Tests
8. README/release notes

Do not combine large architecture changes with product behavior changes.

## Testing Standards

Run focused tests first, then full suite.

Common commands:

```powershell
python -m py_compile ai_pm_agent.py
python -m pytest -q
```

For new modules, add dedicated tests under `tests/`.

Tests must cover:

- happy path
- missing input
- stale data
- weak evidence
- forbidden side effects
- CLI behavior
- output schema stability

## Codex Operating Rules

When working in goal mode:

- inspect relevant files before editing
- make a short plan
- keep changes scoped
- run tests
- write a completion report
- stop and explain if blocked by missing context
- do not invent repo behavior
