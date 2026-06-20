"""Opt-in autopm foundation.

The autopm package is inert by default. It defines schemas, policy defaults,
and fixture-only data-provider contracts for future automatic PM workflows.
It does not wire into review-first modules, broker systems, or execution.
"""

from ai_pm_agent.autopm.data_contracts import (
    EvidenceSnapshot,
    EstimateSnapshot,
    FundamentalSnapshot,
    MarketSnapshot,
    NewsCatalystSnapshot,
    PortfolioInputSnapshot,
    TechnicalSnapshot,
)
from ai_pm_agent.autopm.models import (
    AUTOPM_SCHEMA_VERSION,
    AutopmMode,
    AutopmRunManifest,
    DataProviderLevel,
    EvidenceGateResult,
    PortfolioAwareRecommendation,
    PortfolioGateResult,
    PositionSizingDecision,
    RebalanceProposal,
    RecommendationAction,
    RedTeamResult,
    RiskGateResult,
    StockPickerScore,
    ValuationGateResult,
)
from ai_pm_agent.autopm.policy import AutopmPolicy, default_policy
from ai_pm_agent.autopm.providers import (
    FixtureEstimateDataProvider,
    FixtureFundamentalDataProvider,
    FixtureMarketDataProvider,
    FixtureProviderError,
)

__all__ = [
    "AUTOPM_SCHEMA_VERSION",
    "AutopmMode",
    "AutopmPolicy",
    "AutopmRunManifest",
    "DataProviderLevel",
    "EvidenceGateResult",
    "EvidenceSnapshot",
    "EstimateSnapshot",
    "FixtureEstimateDataProvider",
    "FixtureFundamentalDataProvider",
    "FixtureMarketDataProvider",
    "FixtureProviderError",
    "FundamentalSnapshot",
    "MarketSnapshot",
    "NewsCatalystSnapshot",
    "PortfolioAwareRecommendation",
    "PortfolioGateResult",
    "PortfolioInputSnapshot",
    "PositionSizingDecision",
    "RebalanceProposal",
    "RecommendationAction",
    "RedTeamResult",
    "RiskGateResult",
    "StockPickerScore",
    "TechnicalSnapshot",
    "ValuationGateResult",
    "default_policy",
]
