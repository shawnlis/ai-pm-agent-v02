from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.autopm.models import AutopmMode
from ai_pm_agent.autopm.policy import AutopmPolicy, default_policy


def test_default_policy_keeps_autopm_disabled() -> None:
    policy = default_policy()

    assert policy.mode == AutopmMode.DISABLED


def test_policy_defaults_are_stable() -> None:
    policy = default_policy()

    assert policy == AutopmPolicy(
        mode=AutopmMode.DISABLED,
        max_single_name_weight_pct=5.0,
        max_theme_weight_pct=25.0,
        max_region_weight_pct=50.0,
        max_leverage_adjusted_exposure_pct=100.0,
        min_cash_pct=2.0,
        max_new_position_pct=3.0,
        max_add_pct_per_run=2.0,
        trim_threshold_pct=1.0,
        sell_allowed=False,
        require_evidence_gate=True,
        require_valuation_gate=True,
        require_portfolio_gate=True,
        require_red_team_gate=True,
    )


def test_required_policy_gates_are_enabled_by_default() -> None:
    policy = default_policy()

    assert policy.require_evidence_gate is True
    assert policy.require_valuation_gate is True
    assert policy.require_portfolio_gate is True
    assert policy.require_red_team_gate is True
    assert policy.sell_allowed is False
