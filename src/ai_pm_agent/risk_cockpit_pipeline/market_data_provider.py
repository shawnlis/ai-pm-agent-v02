"""Market data provider abstractions for Risk Cockpit Pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ai_pm_agent.risk_cockpit_pipeline.models import MarketDataProviderSnapshot


class MarketDataProvider(Protocol):
    provider_name: str
    provider_level: str
    network_access: bool
    live_market_data: bool
    fixture_only: bool

    def load(self, path: str | Path) -> MarketDataProviderSnapshot:
        """Load a provider snapshot from a local source."""
