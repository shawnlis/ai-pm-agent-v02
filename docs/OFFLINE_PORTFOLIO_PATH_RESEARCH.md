# Offline portfolio path research

This module compares explicit deterministic portfolio conditions using local inputs.
It does not fetch holdings, prices, account information or funding rates and cannot
place orders. Generated results are conditional arithmetic, not forecasts,
historical alpha, calibrated probabilities, VaR or liquidation levels.

The existing review-first project modules are unchanged. The CLI defaults to
`review_first`, which writes reconciliation and provenance only. Scenario
comparisons require `--mode autopm` plus an explicit research-only config.
No result is marked as a valid automatic investment recommendation.

## Run the synthetic example

From the repository root in PowerShell:

```powershell
$env:PYTHONPATH = "src"
python scripts/portfolio_path_stress.py --snapshot examples/portfolio_path_stress/synthetic_snapshot.json --config examples/portfolio_path_stress/synthetic_config.json --now 2026-10-02T12:01:00Z --output reports/synthetic_path_research
python scripts/portfolio_path_stress.py --snapshot examples/portfolio_path_stress/synthetic_snapshot.json --config examples/portfolio_path_stress/synthetic_config.json --now 2026-10-02T12:01:00Z --output reports/synthetic_path_comparison --mode autopm
python -m pytest -q tests/test_portfolio_path_stress.py
```

The example contains invented quantities, prices, balances, rates and a fictitious
option. It is not an actual portfolio. Results belong under ignored `reports/`.
Never stage private inputs, private configs, outputs, reports or recomputation ZIPs.

## Input contract

The local snapshot has four required keys: `retrieved_utc`,
`get_account_summary`, `get_account_balances`, `get_account_positions`.
The example shows their exact shape. Only USD base accounts, long STK rows
and USD short OPT marks are supported. STK includes funds and depositary receipts.
Unsupported instrument types, missing FX and inconsistent quantity/price units
fail closed. FX CASH position rows and BASE aggregates are excluded from cash
summation. No stock split or DR share conversion is applied to the current mark.

The config explicitly declares `provider_level`: 0 for synthetic fixtures,
3 for a local authorized read-only import. Level 3 also requires
`allow_private_input: true`. Every input retains source, retrieval time,
SHA256, freshness status and warning codes. Unknown broker valuation timestamps
and delay flags block valid investment outputs even when retrieval is recent.
Old snapshots require an explicit retrospective `allow_stale_scenario` override.

Every holding requires an explicit conditional factor mapping. Each scenario
supplies factor endpoint returns, log alternating amplitudes, optional first
leg troughs, FX changes, and funding-rate shifts. These are assumptions, not
market observations or fitted betas. No unspecified holding has a data fallback.

## Comparisons and accounting

- Current portfolio.
- Exit SOXL with explicit USD then foreign-currency repayment.
- Repay every negative currency balance by proportionally reducing other long
  securities while keeping TQQQ, SOXL and short puts.
- Counterfactual QQQ, or equal QQQ/TQQQ with calendar-quarter rebalancing.
- Foreign-currency repayment and common short-put overlay controls.

Stock marks and currency cash balances retain their native units. An unexplained
NAV difference remains a fixed, noninvestable USD bridge. Initial transformations
conserve NAV after explicitly charged costs. Positive cash earns zero in this
model. Settlement delays and broker account-segment netting are not modeled.

Leveraged funds use each day's index return, then subtract a separately supplied
expense and incremental financing assumption:
`V_next = V * (1 + L*r - expense*dt - (L-1)*(reference+spread)*dt)`.
Do not supply already fee-adjusted ETF returns as the index path and deduct
those same costs again. A one-day loss beyond the model's leverage limit ends
the simulation with an error; no survival floor is invented.

External interest uses supplied native-currency tiers, calendar days and day-count
bases. Accruals are posted at modeled month ends. Fund financing is independent
of external account borrowing. Costs apply consistently to initial security
changes, currency conversion and both sides of quarterly turnover.
Calendar-quarter rebalancing uses the last supplied session before the quarter
changes, rather than an assumed fixed number of trading days. The caller supplies
the holiday calendar; asynchronous foreign-market timing is a stated model gap.

## Options and boundaries

Contract fields must be supplied from known information. An implied valuation
multiplier alone is not a verified deliverable. Missing contractual fields require
`allow_conditional_100: true`; adjusted deliverables are unsupported.
Under this conditional branch, expiry assignment debits USD strike cash and adds
100 underlying units per contract if the conditional underlying price is below
strike. Delivered shares then follow the same supplied path. Repaying debt at the
start does not stop later assignment from re-creating debt.

Pre-expiry marks remain frozen by default for compatibility. Optional
`option_valuation: "anchored_european"` requires each contract to supply
`annual_iv`, `risk_free_rate` and `dividend_yield`. A scenario may then supply
`option_iv_shift` in absolute annual volatility units (0.20 means 20 percentage
points), applied from the first modeled session. Missing or invalid inputs fail
closed. This offline sensitivity does not fetch or calibrate IV.

The proxy uses European Black-Scholes value plus the initial observed mark/model
difference, decaying linearly with remaining calendar time. Initial NAV keeps
the observed mark; subsequent marks have an intrinsic floor and strike cap.
Those envelopes do not price American early exercise or discrete dividends.
The proxy converges to intrinsic at expiry, where existing physical assignment
accounting removes the liability and adds shares/debt exactly once. Model value
and initial mark can differ because their inputs have different observation times.
Daily path records include pending option liability for audit.

Path drawdown remains a conditional grid proxy, not a broker margin or liquidation
simulation. Early exercise is omitted. Benchmark option closures use snapshot marks plus
an explicitly assumed gap; this is not an executable option price.
No new premiums, bid/ask prices, IV, funding quotes, probabilities or optimized
weights are fabricated.

## Artifacts and validation

The CLI produces source, policy and run manifests plus reconciliation.
Explicit scenario mode also produces initial-state accounting, a JSON path file
and a stable summary CSV. Strict investment validation stays blocked; arithmetic
validation does not imply investment approval. Source/config/engine hashes
support replay, and source files are never rewritten.

Synthetic tests cover daily compounding, cash/FX accounting, tiered financing,
initial NAV conservation, conditional contracts, assignment financing, missing
and stale inputs, weak evidence gates, default CLI behavior, output schema,
network prohibition and input immutability. Taxes, exact executions, margin
requirements, executable American option prices and calibrated historical win rates
remain outside scope. Option tests cover a standard Black-Scholes reference,
direction/volatility sensitivities, basis convergence, explicit opt-in, initial NAV
and unchanged post-expiry financing/assignment accounting.
