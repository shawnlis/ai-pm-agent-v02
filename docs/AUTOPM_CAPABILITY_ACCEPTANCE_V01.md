# Autopm Capability Acceptance v0.1

## Purpose

This document defines machine-checkable acceptance criteria for the autopm
investment framework before stock picking, portfolio-aware recommendations,
sizing, or rebalance logic are implemented.

This PR is acceptance/testing focused. It does not add a stock picker,
recommender, broker adapter, live provider, CLI, claim audit, output validator,
paper portfolio, monitor, or execution behavior.

## Core Principle

Autopm output quality cannot be guaranteed by model confidence or green tests
alone. The system must prove that investment conclusions are:

- source-backed
- reproducible
- policy-constrained
- blocked when evidence is missing, stale, or weak
- explainable through fields that later claim-audit and output-validation PRs
  can enforce

## Capability Matrix

| Investment capability | Required autopm fields | Acceptance standard |
| --- | --- | --- |
| Business model | `business_model_summary`, `profit_pool`, `reason_codes` | Non-empty; source-backed or explicitly marked as inference |
| Unit economics | `unit_economics_score`, `gross_margin_driver` | Missing data cannot support high score |
| Growth quality | `growth_quality_score`, `growth_drivers` | Must separate volume, price, mix, acquisition, and one-time factors |
| Moat / competition | `moat_score`, `competition_risks` | Must include at least one source-backed support or risk |
| Industry cycle | `industry_cycle_score`, `cycle_stage` | Must identify cycle stage or explicit data gap |
| Financial quality | `financial_quality_score`, `gross_margin_fcf_quality_score` | Must use margin, FCF, inventory, or receivables evidence |
| Capital structure | `capital_structure_score`, `leverage_warnings` | Must expose leverage/debt risk or an explicit no-gap flag |
| Management / governance | `management_governance_score`, `governance_warnings` | Must include source-backed support, warning, or explicit data gap |
| Market expectation gap | `market_expectation_gap_score`, `priced_in_risk` | Price move outpacing EPS revision must trigger penalty |
| Technical / flow signals | `momentum_technical_score`, `market_data_stale` | Stale price data must block valuation-dependent buy/add |
| Valuation | `valuation_score`, `valuation_basis`, `valuation_gate` | Missing valuation blocks buy/add |
| Thesis kill triggers | `thesis_kill_triggers` | Every buy/add-style expected outcome needs kill triggers |
| Portfolio fit | `portfolio_fit_score`, `target_weight_pct`, `max_position_pct` | Target weight must respect policy caps; concentration breach blocks add |
| Asia AI Hardware bottleneck | `bottleneck_score`, `subsector` | Bottleneck scoring must be explicit by subsector |
| AI revenue migration | `ai_revenue_migration_score`, `ai_revenue_share`, `ai_revenue_share_slope` | Migration requires evidence; story-only claims cannot top-rank |
| Customer certification / order visibility | `certification_stage`, `order_visibility_quarters` | Sample is not qualification; qualification is not volume production; volume production is not material revenue without evidence |
| Gross margin / FCF quality | `gross_margin_fcf_quality_score`, `working_capital_warnings` | Inventory/receivables deterioration must trigger risk penalty |
| Valuation expectation gap | `valuation_expectation_gap_score`, `priced_in_penalty` | Price move outpacing EPS revision must trigger priced-in penalty |

## Required Fixture Cases

The fixture pack under `tests/fixtures/autopm_capability/` must include:

- high-quality AI bottleneck company with strong evidence and reasonable valuation
- story-only AI company with weak evidence
- sample-stage company
- qualification-stage company
- volume production without material revenue evidence
- strong company missing valuation
- strong company with stale market data
- company with working-capital deterioration
- company blocked by portfolio concentration
- overweight existing holding requiring hold/trim
- thesis-broken holding requiring sell/trim if policy allows

## Release Gate Candidates

These acceptance tests are not the final claim-audit layer, but they define
the required future gates:

1. Every buy/add-style expected outcome requires source-backed reason codes.
2. Missing valuation blocks buy/add.
3. Stale market data blocks valuation-dependent buy/add.
4. Story-only AI claims cannot rank `top_pick`.
5. Sample does not equal qualification.
6. Qualification does not equal volume production.
7. Volume production does not equal material revenue without explicit evidence.
8. Working-capital deterioration triggers risk penalty.
9. Price move outpacing EPS revision triggers priced-in penalty.
10. Portfolio concentration blocks add.
11. `target_weight_pct` respects policy caps.
12. Every buy/add-style expected outcome has thesis kill triggers.
13. Every recommendation-like output has `required_next_evidence` or an
    explicit no-gap flag.

## What This PR Does Not Prove

This acceptance layer does not prove investment performance, alpha generation,
ranking quality, drawdown control, or recommendation accuracy. It only proves
that the framework can be expressed as machine-checkable inputs and expected
outputs before runtime decision logic exists.

Future PRs must add:

- claim audit
- output validator
- stock picker scoring
- portfolio-aware recommender
- backtest and paper evaluation
