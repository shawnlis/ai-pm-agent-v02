# Autopm Asia AI Hardware Strategy v0.1

## Purpose

This strategy plugin adds deterministic Asia AI Hardware ranking logic on top
of the generic stock picker foundation.

The strategy is ranking-only. It produces stock picker tiers, factor
breakdowns, warnings, data gaps, and source metadata. It does not produce PM
instructions, position sizing, portfolio-aware output, rebalance rows, CLI
runtime behavior, live data calls, broker reads, or broker execution.

## Taxonomy

The strategy supports these subsectors:

- `CCL_M8_M9`
- `PPO_HVLP_GLASS_CLOTH`
- `AI_PCB_SWITCH_BOARD`
- `OPTICS_PACKAGING_CONNECTOR`
- `LIQUID_COOLING_POWER`
- `ODM_AI_SERVER`
- `CLOUD_ASIC_DESIGN_SERVICE`
- `HIGH_SPEED_CONNECTOR_COPPER`
- `ADVANCED_PACKAGING_SUBSTRATE`

## Factor Weights

| Factor | Weight |
| --- | ---: |
| `bottleneck_score` | 30% |
| `ai_revenue_migration_score` | 25% |
| `customer_certification_order_visibility_score` | 20% |
| `gross_margin_fcf_quality_score` | 15% |
| `valuation_expectation_gap_score` | 10% |

## Leading Indicators

The plugin uses fixture/provider fields for:

- AI revenue share
- AI revenue share slope
- customer certification stage
- sample, qualification, small batch, volume production, and material revenue
- order visibility quarters
- high-end capacity expansion
- gross margin trend
- FCF conversion
- contract liabilities or prepayment
- inventory growth versus revenue growth
- receivables growth versus revenue growth
- ASP trend
- EPS revision versus price move
- valuation label
- customer concentration risk
- second-source risk

## Fail-Closed Semantics

- Story-only AI claims cannot reach the top tier.
- Sample stage is not qualification stage.
- Qualification stage is not volume production.
- Volume production is not material revenue without explicit evidence.
- Missing valuation evidence blocks the top tier.
- Stale market data blocks valuation-dependent top-tier ranking.
- Working-capital deterioration penalizes quality.
- Price movement that materially outpaces earnings revisions triggers
  priced-in risk.

## Output Boundary

Rows include:

- `ticker`
- `company_name`
- `market`
- `subsector`
- `rank`
- `total_score`
- `tier`
- `factor_scores`
- `leading_indicators`
- `reason_codes`
- `risk_warnings`
- `data_gaps`
- `red_flags`
- `thesis_validation_triggers`
- `thesis_kill_triggers`
- `downgrade_triggers`
- `required_next_evidence`
- `source_hashes`
- `source_refs`
- `not_recommendation_until_recommender`

The boundary flag marks each row as stock-picker ranking output only.
