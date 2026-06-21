"""Autopm rebalance proposal generation.

Rebalance artifacts are proposals only. This module does not place orders,
connect to brokers, create CLI commands, or write files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ai_pm_agent.autopm.models import AUTOPM_SCHEMA_VERSION, RecommendationAction, RebalanceProposal
from ai_pm_agent.autopm.policy import AutopmPolicy, default_policy


ACTION_PRIORITY = {
    RecommendationAction.SELL.value: 0,
    RecommendationAction.TRIM.value: 1,
    RecommendationAction.BUY.value: 2,
    RecommendationAction.ADD.value: 3,
    RecommendationAction.HOLD.value: 4,
    RecommendationAction.WATCH.value: 5,
    RecommendationAction.MANUAL_REVIEW.value: 6,
    RecommendationAction.AVOID.value: 7,
}
EXECUTABLE_PROPOSAL_ACTIONS = {
    RecommendationAction.BUY.value,
    RecommendationAction.ADD.value,
    RecommendationAction.TRIM.value,
    RecommendationAction.SELL.value,
}
NON_ACTIONABLE_ACTIONS = {
    RecommendationAction.HOLD.value,
    RecommendationAction.WATCH.value,
    RecommendationAction.MANUAL_REVIEW.value,
    RecommendationAction.AVOID.value,
}


@dataclass(frozen=True)
class ExposureSnapshot:
    theme: dict[str, float] = field(default_factory=dict)
    region: dict[str, float] = field(default_factory=dict)
    sector: dict[str, float] = field(default_factory=dict)
    issuer: dict[str, float] = field(default_factory=dict)
    leverage_adjusted_exposure_pct: float = 0.0


@dataclass(frozen=True)
class RebalanceProposalResult:
    proposal: RebalanceProposal
    exposure_before: ExposureSnapshot
    exposure_after: ExposureSnapshot
    concentration_warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": AUTOPM_SCHEMA_VERSION,
            "as_of_date": self.proposal.as_of_date,
            "starting_cash_pct": self.proposal.starting_cash_pct,
            "ending_cash_pct": self.proposal.ending_cash_pct,
            "proposed_trades": list(self.proposal.proposed_trades),
            "blocked_recommendations": list(self.proposal.blocked_recommendations),
            "not_executed": self.proposal.not_executed,
            "theme_exposure_before_after": _before_after(self.exposure_before.theme, self.exposure_after.theme),
            "region_exposure_before_after": _before_after(self.exposure_before.region, self.exposure_after.region),
            "sector_exposure_before_after": _before_after(self.exposure_before.sector, self.exposure_after.sector),
            "issuer_exposure_before_after": _before_after(self.exposure_before.issuer, self.exposure_after.issuer),
            "risk_budget_before": self.exposure_before.leverage_adjusted_exposure_pct,
            "risk_budget_after": self.exposure_after.leverage_adjusted_exposure_pct,
            "concentration_warnings": list(self.concentration_warnings),
        }


def build_rebalance_proposal(
    recommendations: list[dict[str, Any]],
    *,
    as_of_date: str,
    starting_cash_pct: float,
    exposure_before: ExposureSnapshot | None = None,
    policy: AutopmPolicy | None = None,
    estimated_portfolio_value: float = 100000.0,
) -> RebalanceProposalResult:
    """Aggregate recommendations into non-executed proposal rows."""

    policy_obj = policy or default_policy()
    before = exposure_before or ExposureSnapshot()
    ordered = sorted(recommendations, key=lambda rec: (ACTION_PRIORITY.get(_action(rec), 99), _text(rec.get("ticker"))))
    cash_available = float(starting_cash_pct)
    proposed: list[dict[str, object]] = []
    blocked: list[dict[str, object]] = []
    warnings: list[str] = []
    exposure_state = ExposureSnapshot(
        theme=dict(before.theme),
        region=dict(before.region),
        sector=dict(before.sector),
        issuer=dict(before.issuer),
        leverage_adjusted_exposure_pct=before.leverage_adjusted_exposure_pct,
    )

    for rec in ordered:
        row, row_warnings = _proposal_row(
            rec,
            policy=policy_obj,
            cash_available_pct=cash_available,
            estimated_portfolio_value=estimated_portfolio_value,
        )
        warnings.extend(row_warnings)
        exposure_warnings = _apply_exposure_caps(row, exposure_state, policy_obj, estimated_portfolio_value)
        warnings.extend(exposure_warnings)
        delta = float(row["delta_weight_pct"])
        action = str(row["action"])
        manual_review = bool(row["manual_review_required"])
        blocked_by = tuple(row["blocked_by"]) if isinstance(row["blocked_by"], list) else ()

        if blocked_by or manual_review or action in NON_ACTIONABLE_ACTIONS:
            blocked.append(row)
            proposed.append(row)
            continue

        if action in {RecommendationAction.SELL.value, RecommendationAction.TRIM.value}:
            cash_available += abs(delta)
        elif action in {RecommendationAction.BUY.value, RecommendationAction.ADD.value}:
            cash_available -= max(delta, 0.0)
        _update_exposure_state(exposure_state, row)
        proposed.append(row)

    cash_available = max(0.0, round(cash_available, 4))
    after = _apply_exposure_delta(before, proposed)
    proposal = RebalanceProposal(
        as_of_date=as_of_date,
        starting_cash_pct=round(starting_cash_pct, 4),
        ending_cash_pct=cash_available,
        proposed_trades=tuple(proposed),
        blocked_recommendations=tuple(blocked),
        not_executed=True,
    )
    return RebalanceProposalResult(
        proposal=proposal,
        exposure_before=before,
        exposure_after=after,
        concentration_warnings=tuple(dict.fromkeys(warnings)),
    )


def _proposal_row(
    rec: dict[str, Any],
    *,
    policy: AutopmPolicy,
    cash_available_pct: float,
    estimated_portfolio_value: float,
) -> tuple[dict[str, object], list[str]]:
    ticker = _text(rec.get("ticker"))
    action = _action(rec)
    current = _float(rec.get("current_weight_pct"))
    target = min(_float(rec.get("target_weight_pct")), _float(rec.get("max_position_pct"), policy.max_single_name_weight_pct), policy.max_single_name_weight_pct)
    blocked_by = _string_list(rec.get("blocked_by"))
    risk_warnings = _string_list(rec.get("risk_warnings"))
    manual_review = action == RecommendationAction.MANUAL_REVIEW.value or not _bool(rec.get("claim_audit_passed"), default=True)
    warnings: list[str] = []

    if action in {RecommendationAction.BUY.value, RecommendationAction.ADD.value}:
        max_target_from_cash = current + max(0.0, cash_available_pct - policy.min_cash_pct)
        if target > max_target_from_cash:
            target = max(current, max_target_from_cash)
            blocked_by.append("MIN_CASH_LIMIT_EXCEEDED")
            warnings.append("MIN_CASH_LIMIT_EXCEEDED")
        if current == 0.0 and target > policy.max_new_position_pct:
            target = policy.max_new_position_pct
            warnings.append("MAX_NEW_POSITION_APPLIED")
        if current > 0.0 and target - current > policy.max_add_pct_per_run:
            target = current + policy.max_add_pct_per_run
            warnings.append("MAX_ADD_PER_RUN_APPLIED")

    if action in {RecommendationAction.SELL.value, RecommendationAction.TRIM.value} and not policy.sell_allowed:
        target = current
        blocked_by.append("SELL_TRIM_NOT_ALLOWED")
        warnings.append("SELL_TRIM_NOT_ALLOWED")

    if action in NON_ACTIONABLE_ACTIONS:
        target = current
        manual_review = action == RecommendationAction.MANUAL_REVIEW.value

    delta = round(target - current, 4)
    if action in EXECUTABLE_PROPOSAL_ACTIONS and (blocked_by or manual_review):
        executable = False
    else:
        executable = action in EXECUTABLE_PROPOSAL_ACTIONS

    row = {
        "ticker": ticker,
        "action": action,
        "current_weight_pct": round(current, 4),
        "target_weight_pct": round(target, 4),
        "delta_weight_pct": delta,
        "estimated_notional": round(estimated_portfolio_value * delta / 100.0, 2),
        "reason_codes": _reason_codes(rec.get("reason_codes")),
        "risk_warnings": risk_warnings,
        "blocked_by": list(dict.fromkeys(blocked_by)),
        "manual_review_required": manual_review,
        "blocked": bool(blocked_by),
        "executable_proposal": executable,
        "not_executed": True,
        "source_hashes": _string_list(rec.get("source_hashes")),
        "theme": _text(rec.get("theme")),
        "region": _text(rec.get("region")),
        "sector": _text(rec.get("sector")),
        "issuer": _text(rec.get("issuer")),
        "max_position_pct": round(_float(rec.get("max_position_pct"), policy.max_single_name_weight_pct), 4),
        "conviction_score": _float(rec.get("conviction_score")),
        "valuation_gate": rec.get("valuation_gate", {}),
        "valuation_snapshot_present": rec.get("valuation_snapshot_present", True),
        "portfolio_gate": rec.get("portfolio_gate", {}),
        "thesis_kill_triggers": _string_list(rec.get("thesis_kill_triggers")),
    }
    return row, warnings


def _apply_exposure_caps(
    row: dict[str, object],
    exposure_state: ExposureSnapshot,
    policy: AutopmPolicy,
    estimated_portfolio_value: float,
) -> list[str]:
    action = str(row["action"])
    if action not in {RecommendationAction.BUY.value, RecommendationAction.ADD.value}:
        return []
    if row.get("manual_review_required"):
        return []

    delta = max(0.0, float(row["delta_weight_pct"]))
    if delta <= 0:
        return []
    allowed_delta = delta
    warnings: list[str] = []

    theme = str(row.get("theme") or "")
    if theme:
        allowed_delta = min(allowed_delta, max(0.0, policy.max_theme_weight_pct - exposure_state.theme.get(theme, 0.0)))
    region = str(row.get("region") or "")
    if region:
        allowed_delta = min(allowed_delta, max(0.0, policy.max_region_weight_pct - exposure_state.region.get(region, 0.0)))

    if allowed_delta < delta:
        blocked_by = row["blocked_by"] if isinstance(row["blocked_by"], list) else []
        if theme and exposure_state.theme.get(theme, 0.0) + delta > policy.max_theme_weight_pct:
            blocked_by.append("THEME_EXPOSURE_LIMIT_EXCEEDED")
            warnings.append("THEME_EXPOSURE_LIMIT_EXCEEDED")
        if region and exposure_state.region.get(region, 0.0) + delta > policy.max_region_weight_pct:
            blocked_by.append("REGION_EXPOSURE_LIMIT_EXCEEDED")
            warnings.append("REGION_EXPOSURE_LIMIT_EXCEEDED")
        current = float(row["current_weight_pct"])
        row["target_weight_pct"] = round(current + allowed_delta, 4)
        row["delta_weight_pct"] = round(allowed_delta, 4)
        row["estimated_notional"] = round(estimated_portfolio_value * allowed_delta / 100.0, 2)
        row["blocked_by"] = list(dict.fromkeys(blocked_by))
        if allowed_delta <= 0:
            row["blocked"] = True
            row["executable_proposal"] = False
    return warnings


def _update_exposure_state(exposure_state: ExposureSnapshot, row: dict[str, object]) -> None:
    delta = float(row.get("delta_weight_pct") or 0.0)
    _add_bucket(exposure_state.theme, str(row.get("theme") or ""), delta)
    _add_bucket(exposure_state.region, str(row.get("region") or ""), delta)
    _add_bucket(exposure_state.sector, str(row.get("sector") or ""), delta)
    _add_bucket(exposure_state.issuer, str(row.get("issuer") or row.get("ticker") or ""), delta)
    object.__setattr__(
        exposure_state,
        "leverage_adjusted_exposure_pct",
        round(exposure_state.leverage_adjusted_exposure_pct + abs(delta), 4),
    )


def _apply_exposure_delta(before: ExposureSnapshot, rows: list[dict[str, object]]) -> ExposureSnapshot:
    theme = dict(before.theme)
    region = dict(before.region)
    sector = dict(before.sector)
    issuer = dict(before.issuer)
    leverage_delta = 0.0
    for row in rows:
        if row.get("blocked") or row.get("manual_review_required"):
            continue
        delta = float(row.get("delta_weight_pct") or 0.0)
        _add_bucket(theme, str(row.get("theme") or ""), delta)
        _add_bucket(region, str(row.get("region") or ""), delta)
        _add_bucket(sector, str(row.get("sector") or ""), delta)
        _add_bucket(issuer, str(row.get("issuer") or row.get("ticker") or ""), delta)
        leverage_delta += abs(delta)
    return ExposureSnapshot(
        theme={key: round(value, 4) for key, value in sorted(theme.items())},
        region={key: round(value, 4) for key, value in sorted(region.items())},
        sector={key: round(value, 4) for key, value in sorted(sector.items())},
        issuer={key: round(value, 4) for key, value in sorted(issuer.items())},
        leverage_adjusted_exposure_pct=round(before.leverage_adjusted_exposure_pct + leverage_delta, 4),
    )


def _before_after(before: dict[str, float], after: dict[str, float]) -> dict[str, dict[str, float]]:
    keys = sorted(set(before) | set(after))
    return {key: {"before": round(before.get(key, 0.0), 4), "after": round(after.get(key, 0.0), 4)} for key in keys}


def _add_bucket(bucket: dict[str, float], key: str, delta: float) -> None:
    if not key:
        return
    bucket[key] = bucket.get(key, 0.0) + delta


def _action(rec: dict[str, Any]) -> str:
    action = _text(rec.get("action")).lower()
    return action if action else RecommendationAction.MANUAL_REVIEW.value


def _reason_codes(value: Any) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if _text(value):
        return [part.strip() for part in _text(value).replace(";", ",").split(",") if part.strip()]
    return []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "y"}
