"""Write local autopm rebalance proposal report artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from ai_pm_agent.autopm.claim_audit import audit_recommendation_claims
from ai_pm_agent.autopm.models import AUTOPM_SCHEMA_VERSION, AutopmMode
from ai_pm_agent.autopm.output_validator import validate_output_dir
from ai_pm_agent.autopm.rebalance import RebalanceProposalResult


REBALANCE_MD = "AUTOPM_REBALANCE_PROPOSAL.md"
RECOMMENDATIONS_CSV = "autopm_recommendations.csv"
REBALANCE_CSV = "autopm_rebalance_proposal.csv"
POLICY_MANIFEST_JSON = "autopm_policy_manifest.json"
RISK_WARNINGS_MD = "autopm_risk_warnings.md"

RUN_MANIFEST_JSON = "autopm_run_manifest.json"
SOURCE_MANIFEST_JSON = "autopm_source_manifest.json"
RECOMMENDATIONS_JSON = "autopm_recommendations.json"
REBALANCE_JSON = "autopm_rebalance_proposal.json"
CLAIM_AUDIT_JSON = "autopm_claim_audit_summary.json"


def write_rebalance_report(
    out_dir: str | Path,
    *,
    recommendations: list[dict[str, Any]],
    proposal: RebalanceProposalResult,
    policy_manifest: dict[str, Any],
    source_manifest: dict[str, Any],
    run_manifest: dict[str, Any] | None = None,
    output_validation_summary: dict[str, Any] | None = None,
    strict_validation: bool = True,
) -> dict[str, str]:
    """Write local report artifacts under an explicit output directory."""

    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    run_payload = _run_manifest(run_manifest)
    policy_payload = _with_schema(policy_manifest)
    source_payload = _with_schema(source_manifest)
    recommendation_payload = {"schema_version": AUTOPM_SCHEMA_VERSION, "not_executed": True, "recommendations": recommendations}
    rebalance_payload = proposal.to_dict()
    claim_audit = audit_recommendation_claims(_audit_rows(recommendations), source_payload, policy=policy_payload.get("policy", {})).to_dict()
    claim_audit["schema_version"] = AUTOPM_SCHEMA_VERSION

    _write_json(root / RUN_MANIFEST_JSON, run_payload)
    _write_json(root / SOURCE_MANIFEST_JSON, source_payload)
    _write_json(root / POLICY_MANIFEST_JSON, policy_payload)
    _write_json(root / RECOMMENDATIONS_JSON, recommendation_payload)
    _write_json(root / REBALANCE_JSON, rebalance_payload)
    _write_json(root / CLAIM_AUDIT_JSON, claim_audit)
    _write_recommendations_csv(root / RECOMMENDATIONS_CSV, recommendations)
    _write_rebalance_csv(root / REBALANCE_CSV, list(proposal.proposal.proposed_trades))
    (root / REBALANCE_MD).write_text(_render_rebalance_markdown(proposal, output_validation_summary), encoding="utf-8")
    (root / RISK_WARNINGS_MD).write_text(_render_risk_warnings(recommendations, proposal), encoding="utf-8")

    validation = validate_output_dir(root, strict=strict_validation, write_artifacts=True)
    output_files = {
        "rebalance_markdown": str(root / REBALANCE_MD),
        "recommendations_csv": str(root / RECOMMENDATIONS_CSV),
        "rebalance_csv": str(root / REBALANCE_CSV),
        "policy_manifest": str(root / POLICY_MANIFEST_JSON),
        "risk_warnings": str(root / RISK_WARNINGS_MD),
        "run_manifest": str(root / RUN_MANIFEST_JSON),
        "source_manifest": str(root / SOURCE_MANIFEST_JSON),
        "recommendations_json": str(root / RECOMMENDATIONS_JSON),
        "rebalance_json": str(root / REBALANCE_JSON),
        "claim_audit_summary": str(root / CLAIM_AUDIT_JSON),
        "output_validation": str(root / "autopm_output_validation.json"),
    }
    output_files["validation_status"] = validation.status.value
    return output_files


def _run_manifest(payload: dict[str, Any] | None) -> dict[str, Any]:
    merged = {
        "schema_version": AUTOPM_SCHEMA_VERSION,
        "run_id": "autopm-rebalance-fixture",
        "mode": AutopmMode.PROPOSAL.value,
        "strategy_verified": True,
        "execution_enabled": False,
    }
    if payload:
        merged.update(payload)
    merged["schema_version"] = AUTOPM_SCHEMA_VERSION
    merged["execution_enabled"] = False
    return merged


def _with_schema(payload: dict[str, Any]) -> dict[str, Any]:
    merged = dict(payload)
    merged["schema_version"] = AUTOPM_SCHEMA_VERSION
    return merged


def _audit_rows(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [rec for rec in recommendations if rec.get("action") in {"buy", "add", "trim", "sell"}]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_recommendations_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["ticker", "action", "current_weight_pct", "target_weight_pct", "delta_weight_pct", "max_position_pct", "risk_warnings", "not_executed"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, True if field == "not_executed" else "")) for field in fields})


def _write_rebalance_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["ticker", "action", "current_weight_pct", "target_weight_pct", "delta_weight_pct", "estimated_notional", "blocked_by", "manual_review_required", "not_executed"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in fields})


def _render_rebalance_markdown(proposal: RebalanceProposalResult, validation_summary: dict[str, Any] | None) -> str:
    lines = [
        "# AUTOPM Rebalance Proposal",
        "",
        "This is a proposal artifact only. No broker orders were placed.",
        "",
        f"- as_of_date: {proposal.proposal.as_of_date}",
        f"- starting_cash_pct: {proposal.proposal.starting_cash_pct}",
        f"- ending_cash_pct: {proposal.proposal.ending_cash_pct}",
        f"- not_executed: {proposal.proposal.not_executed}",
        "",
        "## Proposed Rows",
        "",
    ]
    for row in proposal.proposal.proposed_trades:
        lines.append(f"- {row['ticker']}: {row['action']} {row['current_weight_pct']} -> {row['target_weight_pct']} (not_executed={row['not_executed']})")
    lines.extend(["", "## Validation", ""])
    if validation_summary:
        lines.append(f"- provided_summary: {validation_summary}")
    else:
        lines.append("- output validation artifacts are written alongside this report")
    return "\n".join(lines) + "\n"


def _render_risk_warnings(recommendations: list[dict[str, Any]], proposal: RebalanceProposalResult) -> str:
    warnings: list[str] = []
    for rec in recommendations:
        for warning in rec.get("risk_warnings", []) if isinstance(rec.get("risk_warnings"), list) else []:
            warnings.append(f"{rec.get('ticker', '')}: {warning}")
    for warning in proposal.concentration_warnings:
        warnings.append(f"portfolio: {warning}")
    lines = ["# AUTOPM Risk Warnings", ""]
    lines.extend(f"- {warning}" for warning in sorted(set(warnings))) if warnings else lines.append("- none")
    lines.append("")
    lines.append("All rows remain not_executed proposal records.")
    return "\n".join(lines) + "\n"


def _csv_value(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ";".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)
