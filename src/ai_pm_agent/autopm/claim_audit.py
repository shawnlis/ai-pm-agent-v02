"""Claim audit gates for autopm outputs.

This module validates recommendation-like artifacts produced by future autopm
workflows. It does not score stocks, create recommendations, read brokers,
fetch live data, or execute orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ai_pm_agent.autopm.models import RecommendationAction
from ai_pm_agent.autopm.policy import AutopmPolicy, default_policy


TRADE_ACTIONS = {
    RecommendationAction.BUY.value,
    RecommendationAction.ADD.value,
    RecommendationAction.TRIM.value,
    RecommendationAction.SELL.value,
}
BUY_ADD_ACTIONS = {RecommendationAction.BUY.value, RecommendationAction.ADD.value}
SEVERE_ALLOWED_ACTIONS = {
    RecommendationAction.MANUAL_REVIEW.value,
    RecommendationAction.WATCH.value,
    RecommendationAction.TRIM.value,
    RecommendationAction.SELL.value,
    RecommendationAction.AVOID.value,
}
HIGH_CONVICTION_THRESHOLD = 0.75
DELTA_TOLERANCE = 0.0001


@dataclass(frozen=True)
class ClaimAuditIssue:
    code: str
    message: str
    severity: str = "error"
    ticker: str = ""


@dataclass
class ClaimAuditResult:
    passed: bool
    issues: list[ClaimAuditIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "issues": [
                {
                    "code": issue.code,
                    "message": issue.message,
                    "severity": issue.severity,
                    "ticker": issue.ticker,
                }
                for issue in self.issues
            ],
        }


def audit_recommendation_claims(
    recommendations: list[dict[str, Any]],
    source_manifest: dict[str, Any] | list[dict[str, Any]],
    *,
    policy: AutopmPolicy | dict[str, Any] | None = None,
    valuation_snapshots: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> ClaimAuditResult:
    """Run all claim-audit gates for recommendation-like rows."""

    issues: list[ClaimAuditIssue] = []
    issues.extend(audit_source_manifest_coverage(recommendations, source_manifest).issues)
    issues.extend(audit_policy_consistency(recommendations, policy=policy, valuation_snapshots=valuation_snapshots).issues)
    issues.extend(audit_output_consistency(recommendations).issues)
    return _result(issues)


def audit_source_manifest_coverage(
    recommendations: list[dict[str, Any]],
    source_manifest: dict[str, Any] | list[dict[str, Any]],
) -> ClaimAuditResult:
    """Verify evidence-backed reason codes resolve to source manifest entries."""

    issues: list[ClaimAuditIssue] = []
    sources = _source_map(source_manifest)
    for rec in recommendations:
        ticker = _text(rec.get("ticker"))
        for reason in _reason_dicts(rec.get("reason_codes")):
            if not _is_evidence_backed(reason):
                continue
            source_hash = _text(reason.get("source_hash"))
            if not source_hash:
                issues.append(_issue("SOURCE_HASH_MISSING", "evidence-backed reason_code requires source_hash", ticker))
                continue
            source = sources.get(source_hash)
            if source is None:
                issues.append(_issue("SOURCE_HASH_UNKNOWN", "source_hash is not present in source_manifest", ticker))
                continue
            if not _text(reason.get("evidence_level")) and not _text(source.get("evidence_level")):
                issues.append(_issue("EVIDENCE_LEVEL_MISSING", "evidence-backed reason_code requires evidence_level", ticker))
            if not (_text(reason.get("source_date")) or _text(source.get("source_date"))):
                warnings = set(_string_list(reason.get("warning_codes"))) | set(_string_list(source.get("warning_codes")))
                if "MISSING_SOURCE_DATE" not in warnings:
                    issues.append(_issue("SOURCE_DATE_MISSING", "source_date missing without MISSING_SOURCE_DATE warning", ticker))
            if _bool(reason.get("stale")) or _bool(source.get("stale")):
                if _float(rec.get("conviction_score")) >= HIGH_CONVICTION_THRESHOLD:
                    issues.append(_issue("STALE_EVIDENCE_HIGH_CONVICTION", "stale evidence cannot support high conviction", ticker))
    return _result(issues)


def audit_policy_consistency(
    recommendations: list[dict[str, Any]],
    *,
    policy: AutopmPolicy | dict[str, Any] | None = None,
    valuation_snapshots: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> ClaimAuditResult:
    """Verify recommendation rows satisfy policy and gate consistency."""

    issues: list[ClaimAuditIssue] = []
    policy_obj = _policy(policy)
    valuation_tickers = _valuation_tickers(valuation_snapshots)
    for rec in recommendations:
        ticker = _text(rec.get("ticker"))
        action = _text(rec.get("action"))
        current_weight = _float(rec.get("current_weight_pct"))
        target_weight = _float(rec.get("target_weight_pct"))
        delta_weight = _float(rec.get("delta_weight_pct"))
        max_position = _float(rec.get("max_position_pct"), default=policy_obj.max_single_name_weight_pct)
        cap = min(max_position, policy_obj.max_single_name_weight_pct)

        if target_weight > cap:
            issues.append(_issue("TARGET_WEIGHT_OVER_CAP", "target_weight_pct exceeds max_position_pct or policy cap", ticker))
        if abs((target_weight - current_weight) - delta_weight) > DELTA_TOLERANCE:
            issues.append(_issue("DELTA_WEIGHT_MISMATCH", "delta_weight_pct must equal target minus current", ticker))
        if action in BUY_ADD_ACTIONS and _gate_failed(rec, "portfolio_gate"):
            issues.append(_issue("PORTFOLIO_GATE_FAILED_BUY_ADD", "buy/add cannot appear if portfolio gate failed", ticker))
        if action in BUY_ADD_ACTIONS and _gate_failed(rec, "valuation_gate"):
            issues.append(_issue("VALUATION_GATE_FAILED_BUY_ADD", "buy/add cannot appear if valuation gate failed", ticker))
        if _bool(rec.get("valuation_dependent")) and action in BUY_ADD_ACTIONS:
            if not (_gate_passed(rec, "valuation_gate") or _bool(rec.get("valuation_snapshot_present")) or ticker in valuation_tickers):
                issues.append(_issue("VALUATION_SNAPSHOT_REQUIRED", "valuation-dependent buy/add requires valuation snapshot or passed valuation gate", ticker))
        if _float(rec.get("conviction_score")) >= HIGH_CONVICTION_THRESHOLD and not _string_list(rec.get("thesis_kill_triggers")):
            issues.append(_issue("THESIS_KILL_TRIGGERS_MISSING", "high-conviction recommendation requires thesis_kill_triggers", ticker))
        if _has_severe_red_team_warning(rec) and action not in SEVERE_ALLOWED_ACTIONS:
            issues.append(_issue("SEVERE_RED_TEAM_ACTION_FORBIDDEN", "severe red-team warning requires review/trim/sell/avoid action", ticker))
    return _result(issues)


def audit_output_consistency(recommendations: list[dict[str, Any]]) -> ClaimAuditResult:
    """Verify generic output consistency for recommendation rows."""

    issues: list[ClaimAuditIssue] = []
    valid_actions = {action.value for action in RecommendationAction}
    for rec in recommendations:
        ticker = _text(rec.get("ticker"))
        action = _text(rec.get("action"))
        if action not in valid_actions:
            issues.append(_issue("INVALID_ACTION", "recommendation action is not a valid enum value", ticker))
        if action in TRADE_ACTIONS and not _reason_dicts(rec.get("reason_codes")):
            issues.append(_issue("REASON_CODES_MISSING", "buy/add/trim/sell recommendation requires reason_codes", ticker))
        if _bool(rec.get("blocked")) and (_bool(rec.get("executable_proposal")) or action in BUY_ADD_ACTIONS):
            issues.append(_issue("BLOCKED_EXECUTABLE_RECOMMENDATION", "blocked recommendation cannot be executable", ticker))
    return _result(issues)


def _result(issues: list[ClaimAuditIssue]) -> ClaimAuditResult:
    return ClaimAuditResult(passed=not any(issue.severity == "error" for issue in issues), issues=issues)


def _source_map(source_manifest: dict[str, Any] | list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if isinstance(source_manifest, dict):
        sources = source_manifest.get("sources", [])
    else:
        sources = source_manifest
    return {
        _text(source.get("source_hash")): source
        for source in sources
        if isinstance(source, dict) and _text(source.get("source_hash"))
    }


def _reason_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    reasons: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            reasons.append(item)
        elif _text(item):
            reasons.append({"code": _text(item), "backing_type": "policy"})
    return reasons


def _is_evidence_backed(reason: dict[str, Any]) -> bool:
    return _text(reason.get("backing_type")) == "source" or bool(_text(reason.get("source_hash")))


def _policy(policy: AutopmPolicy | dict[str, Any] | None) -> AutopmPolicy:
    if isinstance(policy, AutopmPolicy):
        return policy
    if isinstance(policy, dict):
        allowed = {field: policy[field] for field in AutopmPolicy.__dataclass_fields__ if field in policy}
        return AutopmPolicy(**allowed)
    return default_policy()


def _valuation_tickers(value: dict[str, Any] | list[dict[str, Any]] | None) -> set[str]:
    if value is None:
        return set()
    rows = value.get("snapshots", []) if isinstance(value, dict) else value
    return {_text(row.get("ticker")) for row in rows if isinstance(row, dict) and _text(row.get("ticker"))}


def _gate_failed(rec: dict[str, Any], name: str) -> bool:
    value = rec.get(name)
    if isinstance(value, dict):
        return value.get("passed") is False
    return _text(value).lower() in {"failed", "blocked", "false"}


def _gate_passed(rec: dict[str, Any], name: str) -> bool:
    value = rec.get(name)
    if isinstance(value, dict):
        return value.get("passed") is True
    return _text(value).lower() in {"passed", "true"}


def _has_severe_red_team_warning(rec: dict[str, Any]) -> bool:
    warnings = set(_string_list(rec.get("red_team_warnings"))) | set(_string_list(rec.get("risk_warnings")))
    return any(warning.startswith("SEVERE_") or warning == "THESIS_KILL_TRIGGER_ACTIVATED" for warning in warnings)


def _issue(code: str, message: str, ticker: str = "", severity: str = "error") -> ClaimAuditIssue:
    return ClaimAuditIssue(code=code, message=message, ticker=ticker, severity=severity)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    if _text(value):
        return [part.strip() for part in _text(value).replace(";", ",").split(",") if part.strip()]
    return []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y"}
