"""Deterministic autopm sizing logic for recommendation candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_pm_agent.autopm.models import (
    EvidenceGateResult,
    PositionSizingDecision,
    PortfolioGateResult,
    RedTeamResult,
    RiskGateResult,
    StockPickerScore,
    ValuationGateResult,
)
from ai_pm_agent.autopm.policy import AutopmPolicy, default_policy
from ai_pm_agent.autopm.portfolio_policy import AutopmPortfolioPolicy


@dataclass(frozen=True)
class SizingInputs:
    score: StockPickerScore
    current_weight_pct: float
    portfolio_gate: PortfolioGateResult
    evidence_gate: EvidenceGateResult
    valuation_gate: ValuationGateResult
    risk_gate: RiskGateResult
    red_team: RedTeamResult
    policy: AutopmPortfolioPolicy | AutopmPolicy
    market_data_stale: bool = False


@dataclass(frozen=True)
class SizingResult:
    decision: PositionSizingDecision
    blocked_by: tuple[str, ...]
    risk_warnings: tuple[str, ...]
    reason_codes: tuple[str, ...]


def size_position(inputs: SizingInputs) -> SizingResult:
    base_policy = _base_policy(inputs.policy)
    max_position = min(inputs.portfolio_gate.max_position_pct or base_policy.max_single_name_weight_pct, base_policy.max_single_name_weight_pct)
    blocked_by: list[str] = []
    risk_warnings: list[str] = list(inputs.risk_gate.risk_warnings)
    reason_codes: list[str] = []

    if not inputs.evidence_gate.passed or inputs.evidence_gate.score < 0.6:
        blocked_by.append("EVIDENCE_GATE_FAILED")
    if not inputs.valuation_gate.passed:
        blocked_by.append("VALUATION_GATE_FAILED")
    if inputs.market_data_stale or "STALE_MARKET_DATA" in inputs.score.data_gaps or "STALE_MARKET_DATA" in inputs.score.reason_codes:
        blocked_by.append("STALE_MARKET_DATA")
    if not inputs.portfolio_gate.passed:
        blocked_by.append("PORTFOLIO_GATE_FAILED")
        risk_warnings.extend(inputs.portfolio_gate.concentration_warnings)
    if not inputs.risk_gate.passed:
        blocked_by.append("RISK_GATE_FAILED")
    if not inputs.red_team.passed:
        blocked_by.append("RED_TEAM_FAILED")
    if any(warning.startswith("SEVERE_") or warning == "THESIS_KILL_TRIGGER_ACTIVATED" for warning in inputs.red_team.warning_codes):
        blocked_by.append("SEVERE_RED_TEAM_WARNING")

    if blocked_by:
        target = _blocked_target(inputs, base_policy)
        reason_codes.append("SIZING_BLOCKED")
    else:
        target = _target_from_conviction(inputs, max_position, base_policy)
        reason_codes.append("SIZING_POLICY_PASS")

    target = round(max(0.0, min(target, max_position)), 4)
    delta = round(target - inputs.current_weight_pct, 4)
    decision = PositionSizingDecision(
        ticker=inputs.score.ticker,
        current_weight_pct=round(inputs.current_weight_pct, 4),
        target_weight_pct=target,
        delta_weight_pct=delta,
        max_position_pct=round(max_position, 4),
        reason_codes=tuple(reason_codes),
        blocked_by=tuple(dict.fromkeys(blocked_by)),
    )
    return SizingResult(
        decision=decision,
        blocked_by=decision.blocked_by,
        risk_warnings=tuple(dict.fromkeys(risk_warnings)),
        reason_codes=tuple(reason_codes),
    )


def _target_from_conviction(inputs: SizingInputs, max_position: float, policy: AutopmPolicy) -> float:
    conviction = max(0.0, min(1.0, inputs.score.score))
    evidence_multiplier = max(0.35, min(1.0, inputs.evidence_gate.score))
    valuation_multiplier = max(0.35, min(1.0, inputs.valuation_gate.score))
    risk_multiplier = max(0.25, min(1.0, inputs.risk_gate.score))
    base_target = max_position * conviction * evidence_multiplier * valuation_multiplier * risk_multiplier
    base_target = max(base_target, 0.0)

    if inputs.current_weight_pct == 0.0:
        return min(base_target, policy.max_new_position_pct)
    if base_target > inputs.current_weight_pct:
        return min(base_target, inputs.current_weight_pct + policy.max_add_pct_per_run)
    return base_target


def _blocked_target(inputs: SizingInputs, policy: AutopmPolicy) -> float:
    severe = "SEVERE_RED_TEAM_WARNING" in inputs.red_team.warning_codes or "THESIS_KILL_TRIGGER_ACTIVATED" in inputs.red_team.warning_codes
    if (not inputs.red_team.passed or severe) and policy.sell_allowed:
        return 0.0
    if "PORTFOLIO_GATE_FAILED" in inputs.portfolio_gate.reason_codes:
        return inputs.current_weight_pct
    return inputs.current_weight_pct


def _base_policy(policy: AutopmPortfolioPolicy | AutopmPolicy) -> AutopmPolicy:
    if isinstance(policy, AutopmPortfolioPolicy):
        return policy.base_policy
    return policy


def sizing_inputs_from_mapping(row: dict[str, Any]) -> SizingInputs:
    return SizingInputs(
        score=row["score"],
        current_weight_pct=float(row.get("current_weight_pct", 0.0)),
        portfolio_gate=row["portfolio_gate"],
        evidence_gate=row["evidence_gate"],
        valuation_gate=row["valuation_gate"],
        risk_gate=row["risk_gate"],
        red_team=row["red_team"],
        policy=row.get("policy") or default_policy(),
        market_data_stale=bool(row.get("market_data_stale", False)),
    )
