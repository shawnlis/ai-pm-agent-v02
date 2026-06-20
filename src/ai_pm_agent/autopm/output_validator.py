"""Validate autopm run output directories.

The validator checks explicit local output artifacts and writes validation
artifacts. It does not generate recommendations, place orders, connect to
brokers, fetch live data, call LLMs, or use network access.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from enum import StrEnum
import json
from pathlib import Path
from typing import Any

from ai_pm_agent.autopm.claim_audit import audit_recommendation_claims
from ai_pm_agent.autopm.models import AUTOPM_SCHEMA_VERSION, AutopmMode, RecommendationAction
from ai_pm_agent.autopm.policy import default_policy


RUN_MANIFEST_FILE = "autopm_run_manifest.json"
SOURCE_MANIFEST_FILE = "autopm_source_manifest.json"
POLICY_MANIFEST_FILE = "autopm_policy_manifest.json"
RECOMMENDATIONS_FILE = "autopm_recommendations.json"
REBALANCE_PROPOSAL_FILE = "autopm_rebalance_proposal.json"
CLAIM_AUDIT_SUMMARY_FILE = "autopm_claim_audit_summary.json"

VALIDATION_MD = "AUTOPM_OUTPUT_VALIDATION.md"
VALIDATION_JSON = "autopm_output_validation.json"
VALIDATION_CSV = "autopm_output_validation.csv"

OUTPUT_VALIDATION_SCHEMA_VERSION = "autopm_output_validation.v0.1"
FORBIDDEN_EXECUTION_PATTERNS = ("broker", "execution", "order")
SEVERE_WARNING_CODES = {"THESIS_KILL_TRIGGER_ACTIVATED"}


class ValidationStatus(StrEnum):
    VALID = "VALID"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    INVALID = "INVALID"


@dataclass(frozen=True)
class OutputValidationIssue:
    code: str
    message: str
    severity: str = "error"
    file: str = ""
    ticker: str = ""


@dataclass
class OutputValidationResult:
    status: ValidationStatus
    run_dir: str
    issues: list[OutputValidationIssue] = field(default_factory=list)
    files_checked: list[str] = field(default_factory=list)
    output_files: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == ValidationStatus.VALID

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": OUTPUT_VALIDATION_SCHEMA_VERSION,
            "status": self.status.value,
            "run_dir": self.run_dir,
            "files_checked": self.files_checked,
            "output_files": self.output_files,
            "issues": [
                {
                    "code": issue.code,
                    "message": issue.message,
                    "severity": issue.severity,
                    "file": issue.file,
                    "ticker": issue.ticker,
                }
                for issue in self.issues
            ],
        }


def validate_output_dir(run_dir: str | Path, *, strict: bool = False, write_artifacts: bool = True) -> OutputValidationResult:
    """Validate an autopm output directory and optionally write validation artifacts."""

    root = Path(run_dir)
    if not root.exists() or not root.is_dir():
        result = OutputValidationResult(
            status=ValidationStatus.INVALID,
            run_dir=str(root),
            issues=[_issue("RUN_DIR_MISSING", f"run directory does not exist: {root}")],
        )
        return _write_outputs(root, result) if write_artifacts else result

    files_checked: list[str] = []
    issues: list[OutputValidationIssue] = []
    payloads: dict[str, dict[str, Any]] = {}

    for name in (RUN_MANIFEST_FILE, SOURCE_MANIFEST_FILE, POLICY_MANIFEST_FILE):
        files_checked.append(name)
        path = root / name
        if not path.exists():
            issues.append(_issue("REQUIRED_FILE_MISSING", f"required file missing: {name}", file=name))
        else:
            payload, load_issue = _load_json(path)
            if load_issue:
                issues.append(load_issue)
            else:
                payloads[name] = payload

    output_names = [name for name in (RECOMMENDATIONS_FILE, REBALANCE_PROPOSAL_FILE) if (root / name).exists()]
    if not output_names:
        issues.append(_issue("OUTPUT_FILE_MISSING", "recommendations or rebalance proposal output is required"))
    for name in output_names:
        files_checked.append(name)
        payload, load_issue = _load_json(root / name)
        if load_issue:
            issues.append(load_issue)
        else:
            payloads[name] = payload

    claim_summary_path = root / CLAIM_AUDIT_SUMMARY_FILE
    if claim_summary_path.exists():
        files_checked.append(CLAIM_AUDIT_SUMMARY_FILE)
        payload, load_issue = _load_json(claim_summary_path)
        if load_issue:
            issues.append(load_issue)
        else:
            payloads[CLAIM_AUDIT_SUMMARY_FILE] = payload

    issues.extend(_audit_schema_versions(payloads))
    run_manifest = payloads.get(RUN_MANIFEST_FILE, {})
    source_manifest = payloads.get(SOURCE_MANIFEST_FILE, {})
    policy_manifest = payloads.get(POLICY_MANIFEST_FILE, {})
    recommendations = _recommendation_rows(payloads)
    policy = _dict(policy_manifest.get("policy"))
    mode = _text(run_manifest.get("mode"))

    issues.extend(_audit_mode_and_execution_flags(mode, run_manifest, payloads))
    issues.extend(_audit_claim_summary(payloads.get(CLAIM_AUDIT_SUMMARY_FILE), strict=strict))
    issues.extend(_audit_recommendation_output(recommendations, source_manifest, policy))
    issues.extend(_audit_live_strategy_gate(mode, run_manifest))
    issues.extend(_audit_execution_artifacts(root, run_manifest))

    if strict and recommendations and RUN_MANIFEST_FILE in payloads and SOURCE_MANIFEST_FILE in payloads and POLICY_MANIFEST_FILE in payloads:
        claim_result = audit_recommendation_claims(recommendations, source_manifest, policy=policy)
        for claim_issue in claim_result.issues:
            issues.append(
                _issue(
                    f"CLAIM_AUDIT_{claim_issue.code}",
                    claim_issue.message,
                    ticker=claim_issue.ticker,
                    severity=claim_issue.severity,
                )
            )

    result = OutputValidationResult(
        status=_status_from_issues(issues),
        run_dir=str(root),
        issues=issues,
        files_checked=files_checked,
    )
    return _write_outputs(root, result) if write_artifacts else result


def _audit_schema_versions(payloads: dict[str, dict[str, Any]]) -> list[OutputValidationIssue]:
    issues: list[OutputValidationIssue] = []
    for name, payload in payloads.items():
        version = _text(payload.get("schema_version"))
        if not version:
            issues.append(_issue("SCHEMA_VERSION_MISSING", f"schema_version missing in {name}", file=name))
        elif version != AUTOPM_SCHEMA_VERSION:
            issues.append(_issue("SCHEMA_VERSION_MISMATCH", f"{name} schema_version {version} != {AUTOPM_SCHEMA_VERSION}", file=name))
    return issues


def _audit_mode_and_execution_flags(
    mode: str,
    run_manifest: dict[str, Any],
    payloads: dict[str, dict[str, Any]],
) -> list[OutputValidationIssue]:
    issues: list[OutputValidationIssue] = []
    valid_modes = {item.value for item in AutopmMode}
    if mode not in valid_modes:
        issues.append(_issue("OUTPUT_MODE_NOT_EXPLICIT", "run manifest mode must be explicit and valid", file=RUN_MANIFEST_FILE))
        return issues
    if mode in {AutopmMode.PROPOSAL.value, AutopmMode.PAPER.value}:
        for name in (RECOMMENDATIONS_FILE, REBALANCE_PROPOSAL_FILE):
            payload = payloads.get(name)
            if payload is None:
                continue
            if "not_executed" not in payload:
                issues.append(_issue("NOT_EXECUTED_FLAG_MISSING", "proposal/paper output requires not_executed flag", file=name))
            elif payload.get("not_executed") is not True:
                issues.append(_issue("NOT_EXECUTED_FLAG_FALSE", "proposal/paper output must set not_executed=true", file=name))
    if _bool(run_manifest.get("execution_enabled")):
        issues.append(_issue("EXECUTION_MODE_FORBIDDEN", "execution mode is reserved for a future explicit adapter", file=RUN_MANIFEST_FILE))
    return issues


def _audit_claim_summary(claim_summary: dict[str, Any] | None, *, strict: bool) -> list[OutputValidationIssue]:
    if claim_summary is None:
        return []
    if claim_summary.get("passed") is True:
        return []
    severity = "error" if strict else "warning"
    return [_issue("CLAIM_AUDIT_FAILED", "claim audit summary did not pass", severity=severity, file=CLAIM_AUDIT_SUMMARY_FILE)]


def _audit_recommendation_output(
    recommendations: list[dict[str, Any]],
    source_manifest: dict[str, Any],
    policy: dict[str, Any],
) -> list[OutputValidationIssue]:
    issues: list[OutputValidationIssue] = []
    valid_actions = {action.value for action in RecommendationAction}
    source_hashes = {_text(source.get("source_hash")) for source in _list(source_manifest.get("sources"))}
    policy_cap = _float(policy.get("max_single_name_weight_pct"), default_policy().max_single_name_weight_pct)

    for rec in recommendations:
        ticker = _text(rec.get("ticker"))
        action = _text(rec.get("action"))
        target = _float(rec.get("target_weight_pct"))
        max_position = _float(rec.get("max_position_pct"), policy_cap)
        if action not in valid_actions:
            issues.append(_issue("INVALID_ACTION", "recommendation action is not valid", ticker=ticker))
        if target > min(max_position, policy_cap):
            issues.append(_issue("TARGET_WEIGHT_OVER_POLICY", "target weight exceeds policy or row cap", ticker=ticker))
        if _bool(rec.get("blocked")) and (_bool(rec.get("executable_proposal")) or action in {"buy", "add"}):
            issues.append(_issue("BLOCKED_RECOMMENDATION_EXECUTABLE", "blocked recommendation appears executable", ticker=ticker))
        for source_hash in _source_hashes_from_recommendation(rec):
            if source_hash not in source_hashes:
                issues.append(_issue("SOURCE_HASH_UNRESOLVED", "recommendation source_hash not found in source manifest", ticker=ticker))
        for warning in _string_list(rec.get("risk_warnings")) + _string_list(rec.get("red_team_warnings")):
            if _is_severe_warning(warning):
                issues.append(_issue("SEVERE_WARNING_PRESENT", f"severe warning present: {warning}", ticker=ticker, severity="warning"))
    return issues


def _audit_live_strategy_gate(mode: str, run_manifest: dict[str, Any]) -> list[OutputValidationIssue]:
    if mode != AutopmMode.LIVE_RECOMMENDATION.value:
        return []
    if run_manifest.get("strategy_verified") is not True:
        return [_issue("LIVE_RECOMMENDATION_STRATEGY_UNVERIFIED", "unverified strategy cannot enter live_recommendation mode", file=RUN_MANIFEST_FILE)]
    return []


def _audit_execution_artifacts(root: Path, run_manifest: dict[str, Any]) -> list[OutputValidationIssue]:
    execution_enabled = _bool(run_manifest.get("execution_enabled"))
    if execution_enabled:
        return [_issue("EXECUTION_ARTIFACT_GATE_UNIMPLEMENTED", "execution artifacts require a future explicit adapter", file=RUN_MANIFEST_FILE)]
    validation_outputs = {VALIDATION_MD.lower(), VALIDATION_JSON.lower(), VALIDATION_CSV.lower()}
    issues: list[OutputValidationIssue] = []
    for path in root.iterdir():
        if not path.is_file():
            continue
        name = path.name.lower()
        if name in validation_outputs:
            continue
        if any(pattern in name for pattern in FORBIDDEN_EXECUTION_PATTERNS):
            issues.append(_issue("BROKER_EXECUTION_ARTIFACT_FORBIDDEN", f"broker/execution artifact forbidden: {path.name}", file=path.name))
    return issues


def _write_outputs(root: Path, result: OutputValidationResult) -> OutputValidationResult:
    root.mkdir(parents=True, exist_ok=True)
    result.output_files = [VALIDATION_MD, VALIDATION_JSON, VALIDATION_CSV]
    (root / VALIDATION_JSON).write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (root / VALIDATION_MD).write_text(_render_markdown(result), encoding="utf-8")
    with (root / VALIDATION_CSV).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["status", "severity", "code", "message", "file", "ticker"])
        writer.writeheader()
        if not result.issues:
            writer.writerow({"status": result.status.value, "severity": "", "code": "", "message": "", "file": "", "ticker": ""})
        for issue in result.issues:
            writer.writerow(
                {
                    "status": result.status.value,
                    "severity": issue.severity,
                    "code": issue.code,
                    "message": issue.message,
                    "file": issue.file,
                    "ticker": issue.ticker,
                }
            )
    return result


def _render_markdown(result: OutputValidationResult) -> str:
    lines = [
        "# AUTOPM Output Validation",
        "",
        f"- status: {result.status.value}",
        f"- run_dir: {result.run_dir}",
        "",
        "## Issues",
        "",
    ]
    if not result.issues:
        lines.append("- none")
    for issue in result.issues:
        location = f" ({issue.file or issue.ticker})" if issue.file or issue.ticker else ""
        lines.append(f"- [{issue.severity}] {issue.code}{location}: {issue.message}")
    return "\n".join(lines) + "\n"


def _recommendation_rows(payloads: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rec_payload = payloads.get(RECOMMENDATIONS_FILE, {})
    rows.extend(_list(rec_payload.get("recommendations")))
    proposal = payloads.get(REBALANCE_PROPOSAL_FILE, {})
    rows.extend(_list(proposal.get("proposed_trades")))
    return rows


def _source_hashes_from_recommendation(rec: dict[str, Any]) -> list[str]:
    hashes = _string_list(rec.get("source_hashes"))
    for reason in _list(rec.get("reason_codes")):
        source_hash = _text(reason.get("source_hash"))
        if source_hash:
            hashes.append(source_hash)
    return hashes


def _load_json(path: Path) -> tuple[dict[str, Any], OutputValidationIssue | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, _issue("JSON_INVALID", f"invalid JSON: {exc}", file=path.name)
    if not isinstance(payload, dict):
        return {}, _issue("JSON_NOT_OBJECT", "JSON artifact must contain an object", file=path.name)
    return payload, None


def _status_from_issues(issues: list[OutputValidationIssue]) -> ValidationStatus:
    if any(issue.severity == "error" for issue in issues):
        return ValidationStatus.INVALID
    if any(issue.severity == "warning" for issue in issues):
        return ValidationStatus.NEEDS_REVIEW
    return ValidationStatus.VALID


def _issue(
    code: str,
    message: str,
    *,
    severity: str = "error",
    file: str = "",
    ticker: str = "",
) -> OutputValidationIssue:
    return OutputValidationIssue(code=code, message=message, severity=severity, file=file, ticker=ticker)


def _is_severe_warning(warning: str) -> bool:
    return warning.startswith("SEVERE_") or warning in SEVERE_WARNING_CODES


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
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


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y"}
