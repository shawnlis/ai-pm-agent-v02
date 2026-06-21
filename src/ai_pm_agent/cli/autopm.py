"""Explicit local CLI wrapper for autopm workflows.

The CLI orchestrates existing autopm components only. It does not add live
providers, broker reads, order placement, or new investment logic.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import date
import json
from pathlib import Path
from typing import Any

from ai_pm_agent.autopm.asia_ai_hardware import rank_asia_ai_hardware
from ai_pm_agent.autopm.claim_audit import audit_recommendation_claims
from ai_pm_agent.autopm.models import (
    AUTOPM_SCHEMA_VERSION,
    AutopmMode,
    EvidenceGateResult,
    PortfolioGateResult,
    RedTeamResult,
    RiskGateResult,
    StockPickerScore,
    ValuationGateResult,
)
from ai_pm_agent.autopm.output_validator import ValidationStatus, validate_output_dir
from ai_pm_agent.autopm.policy import AutopmPolicy
from ai_pm_agent.autopm.portfolio_loader import AutopmPortfolioLoaderError, assert_safe_autopm_portfolio_path, load_autopm_portfolio
from ai_pm_agent.autopm.portfolio_policy import AutopmPortfolioPolicy
from ai_pm_agent.autopm.rebalance import build_rebalance_proposal
from ai_pm_agent.autopm.recommender import SourceReference, recommend_from_score
from ai_pm_agent.autopm.report_writer import write_rebalance_report
from ai_pm_agent.autopm.stock_picker import rank_stocks


RANKINGS_JSON = "autopm_rankings.json"
RANKINGS_CSV = "autopm_rankings.csv"
RUN_MANIFEST_JSON = "autopm_run_manifest.json"
SOURCE_MANIFEST_JSON = "autopm_source_manifest.json"
POLICY_MANIFEST_JSON = "autopm_policy_manifest.json"
RECOMMENDATIONS_JSON = "autopm_recommendations.json"
CLAIM_AUDIT_JSON = "autopm_claim_audit_summary.json"

ALLOWED_EXECUTION_MODES = {AutopmMode.PROPOSAL.value, AutopmMode.PAPER.value}


class AutopmCliError(ValueError):
    """Raised when autopm CLI inputs fail closed."""


def _add_source_pack_arg(parser: argparse.ArgumentParser, *, required: bool) -> None:
    parser.add_argument("--source-pack", required=required, help="Explicit local fixture/source-pack directory.")


def _add_out_dir_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out-dir", required=True, help="Explicit local output directory.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run explicit local autopm fixture workflows.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_inputs = subparsers.add_parser("validate-inputs", help="Validate source-pack, policy, and portfolio inputs.")
    _add_source_pack_arg(validate_inputs, required=True)
    validate_inputs.add_argument("--strategy", choices=("generic", "asia_ai_hardware"), default="generic")
    validate_inputs.add_argument("--portfolio", help="Optional explicit autopm fixture/local portfolio file.")
    validate_inputs.add_argument("--policy", help="Optional policy manifest JSON.")
    validate_inputs.set_defaults(func=_cmd_validate_inputs)

    rank = subparsers.add_parser("rank", help="Run ranking-only stock picker output.")
    _add_source_pack_arg(rank, required=True)
    rank.add_argument("--strategy", choices=("generic", "asia_ai_hardware"), required=True)
    _add_out_dir_arg(rank)
    rank.set_defaults(func=_cmd_rank)

    recommend = subparsers.add_parser("recommend", help="Run portfolio-aware recommendations from fixture inputs.")
    _add_source_pack_arg(recommend, required=True)
    recommend.add_argument("--strategy", choices=("generic", "asia_ai_hardware"), default="generic")
    recommend.add_argument("--mode", choices=[AutopmMode.DISABLED.value, AutopmMode.PROPOSAL.value, AutopmMode.PAPER.value, AutopmMode.LIVE_RECOMMENDATION.value], required=True)
    recommend.add_argument("--portfolio", required=True, help="Explicit autopm fixture/local portfolio file.")
    recommend.add_argument("--policy", help="Optional policy manifest JSON.")
    _add_out_dir_arg(recommend)
    recommend.set_defaults(func=_cmd_recommend)

    rebalance = subparsers.add_parser("rebalance", help="Write proposal-only rebalance report artifacts.")
    rebalance.add_argument("--mode", choices=[AutopmMode.DISABLED.value, AutopmMode.PROPOSAL.value, AutopmMode.PAPER.value, AutopmMode.LIVE_RECOMMENDATION.value], required=True)
    _add_source_pack_arg(rebalance, required=False)
    rebalance.add_argument("--portfolio", help="Explicit autopm fixture/local portfolio file when recommendations are generated first.")
    rebalance.add_argument("--recommendations", help="Existing recommendations JSON to consume.")
    rebalance.add_argument("--policy", help="Optional policy manifest JSON.")
    rebalance.add_argument("--as-of-date", default=date.today().isoformat())
    rebalance.add_argument("--starting-cash-pct", type=float, default=10.0)
    _add_out_dir_arg(rebalance)
    rebalance.set_defaults(func=_cmd_rebalance)

    validate_output = subparsers.add_parser("validate-output", help="Validate an autopm output directory.")
    validate_output.add_argument("--run-dir", required=True)
    validate_output.add_argument("--strict", action="store_true")
    validate_output.set_defaults(func=_cmd_validate_output)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (AutopmCliError, AutopmPortfolioLoaderError) as exc:
        print(f"ERROR: {exc}")
        return 2


def _cmd_validate_inputs(args: argparse.Namespace) -> int:
    source_pack = _safe_source_pack(args.source_pack)
    _load_candidates(source_pack, args.strategy)
    if args.portfolio:
        assert_safe_autopm_portfolio_path(args.portfolio)
    if args.policy:
        _load_policy_manifest(Path(args.policy))
    print("VALID")
    return 0


def _cmd_rank(args: argparse.Namespace) -> int:
    source_pack = _safe_source_pack(args.source_pack)
    out_dir = _prepare_out_dir(args.out_dir)
    rows = _load_candidates(source_pack, args.strategy)
    rankings = rank_asia_ai_hardware(rows) if args.strategy == "asia_ai_hardware" else rank_stocks(rows)
    payload = {
        "schema_version": AUTOPM_SCHEMA_VERSION,
        "strategy": args.strategy,
        "ranking_only": True,
        "rankings": [_to_dict(item) for item in rankings],
    }
    _write_json(out_dir / RANKINGS_JSON, payload)
    _write_csv(out_dir / RANKINGS_CSV, payload["rankings"], ["rank", "ticker", "company_name", "market", "total_score", "tier"])
    _write_json(out_dir / RUN_MANIFEST_JSON, _run_manifest(mode=AutopmMode.PROPOSAL.value, strategy=args.strategy, command="rank"))
    print(str(out_dir / RANKINGS_JSON))
    return 0


def _cmd_recommend(args: argparse.Namespace) -> int:
    _assert_supported_run_mode(args.mode)
    load_autopm_portfolio(args.portfolio)
    source_pack = _safe_source_pack(args.source_pack)
    out_dir = _prepare_out_dir(args.out_dir)
    source_manifest = _load_source_manifest(source_pack)
    policy_manifest = _policy_for_args(args, source_pack, mode=args.mode)
    recommendations = _build_recommendations(source_pack, source_manifest, policy_manifest, args.mode)
    _write_recommendation_artifacts(out_dir, recommendations, source_manifest, policy_manifest, mode=args.mode, strategy=args.strategy)
    result = validate_output_dir(out_dir, strict=True, write_artifacts=True)
    print(result.status.value)
    return 1 if result.status == ValidationStatus.INVALID else 0


def _cmd_rebalance(args: argparse.Namespace) -> int:
    _assert_supported_run_mode(args.mode)
    out_dir = _prepare_out_dir(args.out_dir)
    if args.recommendations:
        recommendations_payload = _load_json_object(Path(args.recommendations))
        recommendations = _list_of_dicts(recommendations_payload.get("recommendations"))
        source_manifest = _source_manifest_from_payload_or_pack(recommendations_payload, args.source_pack)
        policy_manifest = _policy_for_args(args, Path(args.source_pack) if args.source_pack else None, mode=args.mode)
    else:
        if not args.source_pack or not args.portfolio:
            raise AutopmCliError("rebalance requires --recommendations or explicit --source-pack and --portfolio")
        load_autopm_portfolio(args.portfolio)
        source_pack = _safe_source_pack(args.source_pack)
        source_manifest = _load_source_manifest(source_pack)
        policy_manifest = _policy_for_args(args, source_pack, mode=args.mode)
        recommendations = _build_recommendations(source_pack, source_manifest, policy_manifest, args.mode)
    policy = _policy_from_manifest(policy_manifest, mode=args.mode)
    proposal = build_rebalance_proposal(
        recommendations,
        as_of_date=args.as_of_date,
        starting_cash_pct=args.starting_cash_pct,
        policy=policy,
    )
    files = write_rebalance_report(
        out_dir,
        recommendations=recommendations,
        proposal=proposal,
        policy_manifest=policy_manifest,
        source_manifest=source_manifest,
        run_manifest=_run_manifest(mode=args.mode, strategy="fixture", command="rebalance"),
        strict_validation=True,
    )
    print(files["validation_status"])
    return 1 if files["validation_status"] == ValidationStatus.INVALID.value else 0


def _cmd_validate_output(args: argparse.Namespace) -> int:
    result = validate_output_dir(args.run_dir, strict=args.strict, write_artifacts=True)
    print(result.status.value)
    return 1 if result.status == ValidationStatus.INVALID else 0


def _build_recommendations(
    source_pack: Path,
    source_manifest: dict[str, Any],
    policy_manifest: dict[str, Any],
    mode: str,
) -> list[dict[str, Any]]:
    payload = _load_json_object(source_pack / "recommendation_inputs.json")
    rows = _list_of_dicts(payload.get("rows"))
    if not rows:
        raise AutopmCliError("recommendation_inputs.json requires non-empty rows")
    policy = AutopmPortfolioPolicy(base_policy=_policy_from_manifest(policy_manifest, mode=mode))
    recommendations = []
    for row in rows:
        score = _stock_picker_score(row["score"])
        recommendation = recommend_from_score(
            score,
            current_weight_pct=_float(row.get("current_weight_pct")),
            portfolio_gate=_portfolio_gate(row.get("portfolio_gate")),
            evidence_gate=_evidence_gate(row.get("evidence_gate")),
            valuation_gate=_valuation_gate(row.get("valuation_gate")),
            risk_gate=_risk_gate(row.get("risk_gate")),
            red_team=_red_team(row.get("red_team")),
            source_refs=tuple(_source_ref(item) for item in _list_of_dicts(row.get("source_refs"))),
            source_manifest=source_manifest,
            policy=policy,
            market_data_stale=_bool(row.get("market_data_stale")),
            today=date.fromisoformat(_text(row.get("today")) or date.today().isoformat()),
        )
        recommendations.append(recommendation.to_dict())
    return recommendations


def _write_recommendation_artifacts(
    out_dir: Path,
    recommendations: list[dict[str, Any]],
    source_manifest: dict[str, Any],
    policy_manifest: dict[str, Any],
    *,
    mode: str,
    strategy: str,
) -> None:
    _write_json(out_dir / RUN_MANIFEST_JSON, _run_manifest(mode=mode, strategy=strategy, command="recommend"))
    _write_json(out_dir / SOURCE_MANIFEST_JSON, _with_schema(source_manifest))
    _write_json(out_dir / POLICY_MANIFEST_JSON, _with_schema(policy_manifest))
    _write_json(
        out_dir / RECOMMENDATIONS_JSON,
        {
            "schema_version": AUTOPM_SCHEMA_VERSION,
            "not_executed": True,
            "recommendations": recommendations,
        },
    )
    claim_audit = audit_recommendation_claims(recommendations, _with_schema(source_manifest), policy=_with_schema(policy_manifest).get("policy", {})).to_dict()
    claim_audit["schema_version"] = AUTOPM_SCHEMA_VERSION
    _write_json(out_dir / CLAIM_AUDIT_JSON, claim_audit)


def _safe_source_pack(path: str | Path) -> Path:
    source_pack = Path(path)
    if not source_pack.exists() or not source_pack.is_dir():
        raise AutopmCliError(f"source pack not found: {source_pack}")
    lowered = str(source_pack).lower()
    if any(term in lowered for term in ("ibkr", "broker", "client", "account", "statement", "portfolio.csv")):
        raise AutopmCliError("refusing real-data-looking source pack path")
    return source_pack


def _load_candidates(source_pack: Path, strategy: str) -> list[dict[str, Any]]:
    name = "asia_ai_hardware_candidates.json" if strategy == "asia_ai_hardware" else "generic_candidates.json"
    path = source_pack / name
    if not path.exists():
        path = source_pack / "candidates.json"
    payload = _load_json_object(path)
    rows = _list_of_dicts(payload.get("rows"))
    if not rows:
        raise AutopmCliError(f"{path.name} requires non-empty rows")
    return rows


def _load_source_manifest(source_pack: Path) -> dict[str, Any]:
    path = source_pack / "source_manifest.json"
    if path.exists():
        return _load_json_object(path)
    inputs = _load_json_object(source_pack / "recommendation_inputs.json")
    manifest = _dict(inputs.get("source_manifest"))
    if not manifest:
        raise AutopmCliError("source_manifest.json or recommendation_inputs.source_manifest is required")
    return manifest


def _source_manifest_from_payload_or_pack(payload: dict[str, Any], source_pack: str | None) -> dict[str, Any]:
    manifest = _dict(payload.get("source_manifest"))
    if manifest:
        return manifest
    if source_pack:
        return _load_source_manifest(_safe_source_pack(source_pack))
    raise AutopmCliError("rebalance from recommendations requires source_manifest or --source-pack")


def _policy_for_args(args: argparse.Namespace, source_pack: Path | None, *, mode: str) -> dict[str, Any]:
    if getattr(args, "policy", None):
        payload = _load_policy_manifest(Path(args.policy))
    elif source_pack is not None and (source_pack / "policy_manifest.json").exists():
        payload = _load_policy_manifest(source_pack / "policy_manifest.json")
    else:
        payload = {"policy": asdict(AutopmPolicy(mode=AutopmMode(mode)))}
    payload.setdefault("policy", {})
    payload["policy"]["mode"] = mode
    return payload


def _load_policy_manifest(path: Path) -> dict[str, Any]:
    payload = _load_json_object(path)
    if "policy" not in payload or not isinstance(payload["policy"], dict):
        raise AutopmCliError("policy JSON requires a policy object")
    return payload


def _policy_from_manifest(policy_manifest: dict[str, Any], *, mode: str) -> AutopmPolicy:
    row = dict(_dict(policy_manifest.get("policy")))
    row["mode"] = AutopmMode(mode)
    allowed = set(AutopmPolicy.__dataclass_fields__)
    return AutopmPolicy(**{key: value for key, value in row.items() if key in allowed})


def _run_manifest(*, mode: str, strategy: str, command: str) -> dict[str, Any]:
    return {
        "schema_version": AUTOPM_SCHEMA_VERSION,
        "run_id": f"autopm-cli-{command}-fixture",
        "mode": mode,
        "strategy": strategy,
        "strategy_verified": True,
        "execution_enabled": False,
        "command": command,
    }


def _assert_supported_run_mode(mode: str) -> None:
    if mode not in ALLOWED_EXECUTION_MODES:
        raise AutopmCliError("PR9 supports only proposal or paper mode for recommend/rebalance")


def _prepare_out_dir(path: str | Path) -> Path:
    out_dir = Path(path)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _stock_picker_score(row: dict[str, Any]) -> StockPickerScore:
    return StockPickerScore(
        ticker=_required_text(row, "ticker"),
        company_name=_required_text(row, "company_name"),
        market=_required_text(row, "market"),
        rank=int(_float(row.get("rank"), 1.0)),
        score=_float(row.get("score")),
        tier=_required_text(row, "tier"),
        factor_scores=_dict(row.get("factor_scores")),
        reason_codes=tuple(_string_list(row.get("reason_codes"))),
        data_gaps=tuple(_string_list(row.get("data_gaps"))),
        red_flags=tuple(_string_list(row.get("red_flags"))),
        required_next_evidence=tuple(_string_list(row.get("required_next_evidence"))),
    )


def _source_ref(row: dict[str, Any]) -> SourceReference:
    return SourceReference(
        code=_required_text(row, "code"),
        source_hash=_required_text(row, "source_hash"),
        evidence_level=_required_text(row, "evidence_level"),
        source_date=_required_text(row, "source_date"),
        period=_required_text(row, "period"),
        field=_required_text(row, "field"),
    )


def _evidence_gate(value: Any) -> EvidenceGateResult:
    row = _dict(value)
    return EvidenceGateResult(
        passed=_bool(row.get("passed")),
        score=_float(row.get("score")),
        reason_codes=tuple(_string_list(row.get("reason_codes"))),
        warning_codes=tuple(_string_list(row.get("warning_codes"))),
        required_next_evidence=tuple(_string_list(row.get("required_next_evidence"))),
    )


def _valuation_gate(value: Any) -> ValuationGateResult:
    row = _dict(value)
    return ValuationGateResult(
        passed=_bool(row.get("passed")),
        score=_float(row.get("score")),
        valuation_basis=_text(row.get("valuation_basis")),
        reason_codes=tuple(_string_list(row.get("reason_codes"))),
        warning_codes=tuple(_string_list(row.get("warning_codes"))),
    )


def _risk_gate(value: Any) -> RiskGateResult:
    row = _dict(value)
    return RiskGateResult(
        passed=_bool(row.get("passed")),
        score=_float(row.get("score")),
        risk_warnings=tuple(_string_list(row.get("risk_warnings"))),
        reason_codes=tuple(_string_list(row.get("reason_codes"))),
    )


def _portfolio_gate(value: Any) -> PortfolioGateResult:
    row = _dict(value)
    return PortfolioGateResult(
        passed=_bool(row.get("passed")),
        portfolio_fit_score=_float(row.get("portfolio_fit_score")),
        current_weight_pct=_float(row.get("current_weight_pct")),
        max_position_pct=_float(row.get("max_position_pct")),
        concentration_warnings=tuple(_string_list(row.get("concentration_warnings"))),
        reason_codes=tuple(_string_list(row.get("reason_codes"))),
    )


def _red_team(value: Any) -> RedTeamResult:
    row = _dict(value)
    return RedTeamResult(
        passed=_bool(row.get("passed")),
        strongest_bear_case=_text(row.get("strongest_bear_case")),
        missing_evidence=tuple(_string_list(row.get("missing_evidence"))),
        thesis_kill_triggers=tuple(_string_list(row.get("thesis_kill_triggers"))),
        downgrade_triggers=tuple(_string_list(row.get("downgrade_triggers"))),
        warning_codes=tuple(_string_list(row.get("warning_codes"))),
    )


def _load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise AutopmCliError(f"required JSON file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AutopmCliError(f"JSON file must contain an object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in fields})


def _with_schema(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["schema_version"] = AUTOPM_SCHEMA_VERSION
    return result


def _to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return value
    return dict(value)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _required_text(row: dict[str, Any], key: str) -> str:
    value = _text(row.get(key))
    if not value:
        raise AutopmCliError(f"required value missing: {key}")
    return value


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


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    if _text(value):
        return [part.strip() for part in _text(value).replace(";", ",").split(",") if part.strip()]
    return []


def _csv_value(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ";".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)
