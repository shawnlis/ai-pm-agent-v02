"""Autopm provider data contracts.

Every snapshot carries provenance metadata. These contracts are used by
fixture-only providers in this PR and are ready for future opt-in providers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ai_pm_agent.autopm.models import AUTOPM_SCHEMA_VERSION, DataProviderLevel


@dataclass(frozen=True)
class SnapshotMetadata:
    ticker: str
    provider_name: str
    provider_level: DataProviderLevel
    retrieval_time: str
    as_of_date: str
    source_ids: tuple[str, ...]
    reliability: float
    stale: bool
    warning_codes: tuple[str, ...] = ()
    fixture_only: bool = True
    schema_version: str = AUTOPM_SCHEMA_VERSION


@dataclass(frozen=True)
class MarketSnapshot(SnapshotMetadata):
    price: float = 0.0
    currency: str = ""
    volume: float | None = None


@dataclass(frozen=True)
class FundamentalSnapshot(SnapshotMetadata):
    revenue: float | None = None
    gross_margin_pct: float | None = None
    fcf_margin_pct: float | None = None
    debt_to_equity: float | None = None


@dataclass(frozen=True)
class EstimateSnapshot(SnapshotMetadata):
    next_eps: float | None = None
    eps_revision_pct: float | None = None
    revenue_revision_pct: float | None = None


@dataclass(frozen=True)
class TechnicalSnapshot(SnapshotMetadata):
    price_change_3m_pct: float | None = None
    price_change_12m_pct: float | None = None
    relative_strength: float | None = None


@dataclass(frozen=True)
class NewsCatalystSnapshot(SnapshotMetadata):
    catalyst_summary: str = ""
    catalyst_score: float | None = None


@dataclass(frozen=True)
class EvidenceSnapshot(SnapshotMetadata):
    evidence_level: str = ""
    claim_fields: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioInputSnapshot(SnapshotMetadata):
    current_weight_pct: float = 0.0
    theme: str = ""
    region: str = ""
    sector: str = ""
