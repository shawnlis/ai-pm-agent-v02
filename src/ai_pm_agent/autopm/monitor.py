"""Local state-diff monitor for autopm artifacts.

Alerts are review triggers only. This module does not schedule jobs, send
notifications, fetch live data, connect to brokers, or create trade orders.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from enum import StrEnum
import json
from pathlib import Path
from typing import Any

from ai_pm_agent.autopm.state_store import AutopmRunState, load_monitor_state


ALERTS_MD = "AUTOPM_MONITOR_ALERTS.md"
ALERTS_CSV = "autopm_alerts.csv"
MONITOR_STATE_JSON = "autopm_monitor_state.json"
WARNINGS_MD = "autopm_monitor_warnings.md"


class AlertSeverity(StrEnum):
    INFO = "info"
    WATCH = "watch"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class MonitorAlert:
    alert_id: str
    ticker: str
    alert_type: str
    severity: AlertSeverity
    prior_value: str = ""
    current_value: str = ""
    reason_codes: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    required_next_action: str = "manual_review"
    manual_review_required: bool = True
    not_investment_advice: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "ticker": self.ticker,
            "alert_type": self.alert_type,
            "severity": self.severity.value,
            "prior_value": self.prior_value,
            "current_value": self.current_value,
            "reason_codes": list(self.reason_codes),
            "source_refs": list(self.source_refs),
            "required_next_action": self.required_next_action,
            "manual_review_required": self.manual_review_required,
            "not_investment_advice": self.not_investment_advice,
        }


@dataclass(frozen=True)
class MonitorResult:
    prior_run_id: str
    current_run_id: str
    alerts: tuple[MonitorAlert, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "prior_run_id": self.prior_run_id,
            "current_run_id": self.current_run_id,
            "alerts": [alert.to_dict() for alert in self.alerts],
            "warnings": list(self.warnings),
            "not_investment_advice": True,
            "review_triggers_only": True,
        }


def monitor_explicit_paths(prior_path: str | Path, current_path: str | Path, *, out_dir: str | Path | None = None) -> MonitorResult:
    """Load two explicit states, diff them, and optionally write local artifacts."""

    result = compare_states(load_monitor_state(prior_path), load_monitor_state(current_path))
    if out_dir is not None:
        write_monitor_artifacts(result, out_dir)
    return result


def compare_states(prior: AutopmRunState, current: AutopmRunState) -> MonitorResult:
    alerts: list[MonitorAlert] = []
    alerts.extend(_ranking_alerts(prior, current))
    alerts.extend(_recommendation_alerts(prior, current))
    alerts.extend(_rebalance_alerts(current))
    alerts.extend(_claim_validation_alerts(current))
    alerts.extend(_paper_alerts(prior, current))
    ordered = tuple(sorted(alerts, key=lambda alert: (alert.ticker, alert.alert_type, alert.alert_id)))
    return MonitorResult(prior_run_id=prior.run_id, current_run_id=current.run_id, alerts=ordered)


def write_monitor_artifacts(result: MonitorResult, out_dir: str | Path) -> dict[str, str]:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    rows = [alert.to_dict() for alert in result.alerts]
    (root / MONITOR_STATE_JSON).write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (root / ALERTS_MD).write_text(_render_alerts_md(result), encoding="utf-8")
    (root / WARNINGS_MD).write_text(_render_warnings_md(result), encoding="utf-8")
    with (root / ALERTS_CSV).open("w", encoding="utf-8", newline="") as handle:
        fields = [
            "alert_id",
            "ticker",
            "alert_type",
            "severity",
            "prior_value",
            "current_value",
            "reason_codes",
            "source_refs",
            "required_next_action",
            "manual_review_required",
            "not_investment_advice",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in fields})
    return {
        "alerts_markdown": str(root / ALERTS_MD),
        "alerts_csv": str(root / ALERTS_CSV),
        "monitor_state": str(root / MONITOR_STATE_JSON),
        "warnings_markdown": str(root / WARNINGS_MD),
    }


def _ranking_alerts(prior: AutopmRunState, current: AutopmRunState) -> list[MonitorAlert]:
    prior_rows = {_ticker(row): row for row in prior.rankings}
    current_rows = {_ticker(row): row for row in current.rankings}
    prior_top = {ticker for ticker, row in prior_rows.items() if _text(row.get("tier")) == "top_pick"}
    current_top = {ticker for ticker, row in current_rows.items() if _text(row.get("tier")) == "top_pick"}
    alerts: list[MonitorAlert] = []
    for ticker in current_top - prior_top:
        alerts.append(_alert(ticker, "NEW_TOP_PICK", AlertSeverity.INFO, "", "top_pick", current_rows[ticker]))
    for ticker in prior_top - current_top:
        alerts.append(_alert(ticker, "REMOVED_TOP_PICK", AlertSeverity.WATCH, "top_pick", _text(current_rows.get(ticker, {}).get("tier")), current_rows.get(ticker) or prior_rows[ticker]))
    for ticker in sorted(set(prior_rows) & set(current_rows)):
        prior_rank = _float(prior_rows[ticker].get("rank"))
        current_rank = _float(current_rows[ticker].get("rank"))
        if current_rank and prior_rank and current_rank < prior_rank:
            alerts.append(_alert(ticker, "RANK_UPGRADE", AlertSeverity.INFO, str(int(prior_rank)), str(int(current_rank)), current_rows[ticker]))
        elif current_rank and prior_rank and current_rank > prior_rank:
            alerts.append(_alert(ticker, "RANK_DOWNGRADE", AlertSeverity.WATCH, str(int(prior_rank)), str(int(current_rank)), current_rows[ticker]))
    return alerts


def _recommendation_alerts(prior: AutopmRunState, current: AutopmRunState) -> list[MonitorAlert]:
    prior_rows = {_ticker(row): row for row in prior.recommendations}
    current_rows = {_ticker(row): row for row in current.recommendations}
    alerts: list[MonitorAlert] = []
    for ticker in sorted(set(prior_rows) & set(current_rows)):
        prior_row = prior_rows[ticker]
        current_row = current_rows[ticker]
        prior_action = _text(prior_row.get("action"))
        current_action = _text(current_row.get("action"))
        if _action_score(current_action) > _action_score(prior_action):
            alerts.append(_alert(ticker, "ACTION_UPGRADE", AlertSeverity.WATCH, prior_action, current_action, current_row))
        elif _action_score(current_action) < _action_score(prior_action):
            alerts.append(_alert(ticker, "ACTION_DOWNGRADE", AlertSeverity.WARNING, prior_action, current_action, current_row))
        prior_target = _float(prior_row.get("target_weight_pct"))
        current_target = _float(current_row.get("target_weight_pct"))
        if current_target > prior_target:
            alerts.append(_alert(ticker, "TARGET_WEIGHT_INCREASE", AlertSeverity.WATCH, str(prior_target), str(current_target), current_row))
        elif current_target < prior_target:
            alerts.append(_alert(ticker, "TARGET_WEIGHT_DECREASE", AlertSeverity.WATCH, str(prior_target), str(current_target), current_row))
    for ticker, current_row in sorted(current_rows.items()):
        alerts.extend(_recommendation_diagnostic_alerts(ticker, current_row))
    return alerts


def _recommendation_diagnostic_alerts(ticker: str, current_row: dict[str, Any]) -> list[MonitorAlert]:
    alerts: list[MonitorAlert] = []
    warnings = _strings(current_row.get("risk_warnings")) + _strings(current_row.get("red_team_warnings"))
    if "THESIS_KILL_TRIGGER_ACTIVATED" in warnings:
        alerts.append(_alert(ticker, "THESIS_KILL_TRIGGER_ACTIVE", AlertSeverity.CRITICAL, "", "active", current_row))
    if _strings(current_row.get("required_next_evidence")):
        alerts.append(_alert(ticker, "REQUIRED_EVIDENCE_MISSING", AlertSeverity.WARNING, "", ";".join(_strings(current_row.get("required_next_evidence"))), current_row))
    if any("STALE" in item for item in warnings + _strings(current_row.get("data_gaps"))):
        alert_type = "PRICE_OR_VALUATION_STALE" if any("VALUATION" in item or "PRICE" in item or "MARKET" in item for item in warnings + _strings(current_row.get("data_gaps"))) else "EVIDENCE_STALE"
        alerts.append(_alert(ticker, alert_type, AlertSeverity.WARNING, "", "stale", current_row))
    return alerts


def _rebalance_alerts(current: AutopmRunState) -> list[MonitorAlert]:
    alerts: list[MonitorAlert] = []
    for row in current.rebalance_rows:
        ticker = _ticker(row)
        blocked = _strings(row.get("blocked_by")) + _strings(row.get("risk_warnings"))
        if any("POLICY" in item for item in blocked):
            alerts.append(_alert(ticker, "POLICY_BREACH", AlertSeverity.WARNING, "", ";".join(blocked), row))
        if any("CONCENTRATION" in item or "EXPOSURE" in item for item in blocked):
            alerts.append(_alert(ticker, "CONCENTRATION_BREACH", AlertSeverity.WARNING, "", ";".join(blocked), row))
        if any("CASH" in item for item in blocked):
            alerts.append(_alert(ticker, "CASH_CONSTRAINT", AlertSeverity.WARNING, "", ";".join(blocked), row))
    return alerts


def _claim_validation_alerts(current: AutopmRunState) -> list[MonitorAlert]:
    alerts: list[MonitorAlert] = []
    if current.claim_audit and current.claim_audit.get("passed") is not True:
        alerts.append(_alert("", "CLAIM_AUDIT_FAILED", AlertSeverity.CRITICAL, "", "failed", current.claim_audit))
    status = _text(current.output_validation.get("status")).upper()
    if status == "INVALID":
        alerts.append(_alert("", "OUTPUT_VALIDATION_INVALID", AlertSeverity.CRITICAL, "", status, current.output_validation))
    return alerts


def _paper_alerts(prior: AutopmRunState, current: AutopmRunState) -> list[MonitorAlert]:
    prior_value = _float(prior.paper_state.get("portfolio_value"))
    current_value = _float(current.paper_state.get("portfolio_value"))
    alerts: list[MonitorAlert] = []
    if prior_value and current_value and (prior_value - current_value) / prior_value >= 0.05:
        alerts.append(_alert("", "PAPER_DRAWDOWN_ALERT", AlertSeverity.WARNING, str(prior_value), str(current_value), current.paper_state))
    prior_turnover = _float(prior.paper_state.get("turnover"))
    current_turnover = _float(current.paper_state.get("turnover"))
    if current_turnover >= 0.25 and current_turnover > prior_turnover:
        alerts.append(_alert("", "TURNOVER_ALERT", AlertSeverity.WARNING, str(prior_turnover), str(current_turnover), current.paper_state))
    return alerts


def _alert(ticker: str, alert_type: str, severity: AlertSeverity, prior: str, current: str, row: dict[str, Any]) -> MonitorAlert:
    key = ticker or "PORTFOLIO"
    return MonitorAlert(
        alert_id=f"{key}:{alert_type}",
        ticker=ticker,
        alert_type=alert_type,
        severity=severity,
        prior_value=prior,
        current_value=current,
        reason_codes=tuple(_reason_codes(row)),
        source_refs=tuple(_source_refs(row)),
        required_next_action="manual_review",
        manual_review_required=True,
        not_investment_advice=True,
    )


def _render_alerts_md(result: MonitorResult) -> str:
    lines = [
        "# AUTOPM Monitor Alerts",
        "",
        "Alerts are review triggers only. They are not trade instructions.",
        "",
    ]
    if not result.alerts:
        lines.append("- none")
    for alert in result.alerts:
        ticker = f" {alert.ticker}" if alert.ticker else ""
        lines.append(f"- [{alert.severity.value}] {alert.alert_type}{ticker}: {alert.prior_value} -> {alert.current_value}; next_action=manual_review")
    return "\n".join(lines) + "\n"


def _render_warnings_md(result: MonitorResult) -> str:
    critical = [alert for alert in result.alerts if alert.severity == AlertSeverity.CRITICAL]
    lines = [
        "# AUTOPM Monitor Warnings",
        "",
        "Critical alerts require manual review only; no sell, trim, order, broker, or notification action is triggered.",
        "",
    ]
    if not critical:
        lines.append("- no critical alerts")
    for alert in critical:
        lines.append(f"- {alert.alert_type} {alert.ticker or 'portfolio'}: manual review required")
    return "\n".join(lines) + "\n"


def _ticker(row: dict[str, Any]) -> str:
    return _text(row.get("ticker")).upper()


def _action_score(action: str) -> int:
    order = {"avoid": 0, "watch": 1, "manual_review": 1, "hold": 2, "trim": 2, "sell": 0, "add": 3, "buy": 4}
    return order.get(action, 1)


def _reason_codes(row: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    for item in row.get("reason_codes", []) if isinstance(row.get("reason_codes"), list) else []:
        if isinstance(item, dict):
            codes.append(_text(item.get("code")))
        else:
            codes.append(_text(item))
    return [code for code in codes if code]


def _source_refs(row: dict[str, Any]) -> list[str]:
    refs = _strings(row.get("source_refs")) + _strings(row.get("source_hashes"))
    return sorted(set(refs))


def _strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    if _text(value):
        return [part.strip() for part in _text(value).replace(";", ",").split(",") if part.strip()]
    return []


def _csv_value(value: Any) -> str:
    if isinstance(value, list):
        return ";".join(str(item) for item in value)
    return str(value)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
