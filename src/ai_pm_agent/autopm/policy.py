"""Autopm policy defaults.

Defaults are intentionally conservative and inert. Autopm remains disabled
unless a future command, config, or test explicitly enables it.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_pm_agent.autopm.models import AutopmMode


@dataclass(frozen=True)
class AutopmPolicy:
    mode: AutopmMode = AutopmMode.DISABLED
    max_single_name_weight_pct: float = 5.0
    max_theme_weight_pct: float = 25.0
    max_region_weight_pct: float = 50.0
    max_leverage_adjusted_exposure_pct: float = 100.0
    min_cash_pct: float = 2.0
    max_new_position_pct: float = 3.0
    max_add_pct_per_run: float = 2.0
    trim_threshold_pct: float = 1.0
    sell_allowed: bool = False
    require_evidence_gate: bool = True
    require_valuation_gate: bool = True
    require_portfolio_gate: bool = True
    require_red_team_gate: bool = True


def default_policy() -> AutopmPolicy:
    """Return the default disabled autopm policy."""

    return AutopmPolicy()
