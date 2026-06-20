from __future__ import annotations

from collections.abc import Iterator
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import uuid

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.autopm.models import AUTOPM_SCHEMA_VERSION
from ai_pm_agent.autopm.output_validator import (
    CLAIM_AUDIT_SUMMARY_FILE,
    POLICY_MANIFEST_FILE,
    RECOMMENDATIONS_FILE,
    RUN_MANIFEST_FILE,
    SOURCE_MANIFEST_FILE,
    VALIDATION_CSV,
    VALIDATION_JSON,
    VALIDATION_MD,
    ValidationStatus,
    validate_output_dir,
)


SOURCE_HASH = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


@pytest.fixture
def run_root() -> Iterator[Path]:
    root = Path(".pytest_autopm_output_validator_tmp") / uuid.uuid4().hex
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)
        parent = root.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _recommendation(**overrides: object) -> dict:
    row = {
        "ticker": "TEST",
        "action": "buy",
        "conviction_score": 0.82,
        "current_weight_pct": 0.0,
        "target_weight_pct": 4.0,
        "delta_weight_pct": 4.0,
        "max_position_pct": 5.0,
        "valuation_dependent": True,
        "valuation_gate": {"passed": True},
        "valuation_snapshot_present": True,
        "portfolio_gate": {"passed": True},
        "thesis_kill_triggers": ["guide-down", "margin break", "lost certification"],
        "risk_warnings": [],
        "red_team_warnings": [],
        "blocked": False,
        "executable_proposal": False,
        "source_hashes": [SOURCE_HASH],
        "reason_codes": [
            {
                "code": "AI_REVENUE_MIGRATION_CONFIRMED",
                "backing_type": "source",
                "source_hash": SOURCE_HASH,
                "evidence_level": "primary_official",
                "source_date": "2026-03-31",
                "period": "2026Q1",
                "field": "ai_revenue_share",
            }
        ],
    }
    row.update(overrides)
    return row


def _make_run_dir(
    root: Path,
    *,
    mode: str = "proposal",
    not_executed: bool | None = True,
    claim_passed: bool | None = True,
    recommendation: dict | None = None,
    strategy_verified: bool = False,
) -> Path:
    _write_json(
        root / RUN_MANIFEST_FILE,
        {
            "schema_version": AUTOPM_SCHEMA_VERSION,
            "run_id": "fixture-run",
            "mode": mode,
            "strategy_verified": strategy_verified,
            "execution_enabled": False,
        },
    )
    _write_json(
        root / SOURCE_MANIFEST_FILE,
        {
            "schema_version": AUTOPM_SCHEMA_VERSION,
            "sources": [
                {
                    "source_hash": SOURCE_HASH,
                    "source_date": "2026-03-31",
                    "period": "2026Q1",
                    "evidence_level": "primary_official",
                    "stale": False,
                    "warning_codes": [],
                }
            ],
        },
    )
    _write_json(
        root / POLICY_MANIFEST_FILE,
        {
            "schema_version": AUTOPM_SCHEMA_VERSION,
            "policy": {"max_single_name_weight_pct": 5.0, "sell_allowed": False},
        },
    )
    rec_payload = {
        "schema_version": AUTOPM_SCHEMA_VERSION,
        "recommendations": [recommendation or _recommendation()],
    }
    if not_executed is not None:
        rec_payload["not_executed"] = not_executed
    _write_json(root / RECOMMENDATIONS_FILE, rec_payload)
    if claim_passed is not None:
        _write_json(
            root / CLAIM_AUDIT_SUMMARY_FILE,
            {
                "schema_version": AUTOPM_SCHEMA_VERSION,
                "passed": claim_passed,
                "issues": [] if claim_passed else [{"code": "CLAIM_AUDIT_FAILED"}],
            },
        )
    return root


def _codes(result) -> set[str]:
    return {issue.code for issue in result.issues}


def test_valid_fixture_output_passes(run_root: Path) -> None:
    run_dir = _make_run_dir(run_root)

    result = validate_output_dir(run_dir, strict=True)

    assert result.status == ValidationStatus.VALID
    assert (run_dir / VALIDATION_MD).exists()
    assert (run_dir / VALIDATION_JSON).exists()
    assert (run_dir / VALIDATION_CSV).exists()


def test_missing_run_manifest_invalid(run_root: Path) -> None:
    run_dir = _make_run_dir(run_root)
    (run_dir / RUN_MANIFEST_FILE).unlink()

    result = validate_output_dir(run_dir, strict=True)

    assert result.status == ValidationStatus.INVALID
    assert "REQUIRED_FILE_MISSING" in _codes(result)


def test_missing_source_manifest_invalid(run_root: Path) -> None:
    run_dir = _make_run_dir(run_root)
    (run_dir / SOURCE_MANIFEST_FILE).unlink()

    result = validate_output_dir(run_dir, strict=True)

    assert result.status == ValidationStatus.INVALID
    assert "REQUIRED_FILE_MISSING" in _codes(result)


def test_missing_policy_manifest_invalid(run_root: Path) -> None:
    run_dir = _make_run_dir(run_root)
    (run_dir / POLICY_MANIFEST_FILE).unlink()

    result = validate_output_dir(run_dir, strict=True)

    assert result.status == ValidationStatus.INVALID
    assert "REQUIRED_FILE_MISSING" in _codes(result)


def test_warning_only_output_needs_review(run_root: Path) -> None:
    rec = _recommendation(action="manual_review", risk_warnings=["SEVERE_REVIEW_REQUIRED"])
    run_dir = _make_run_dir(run_root, recommendation=rec)

    result = validate_output_dir(run_dir, strict=True)

    assert result.status == ValidationStatus.NEEDS_REVIEW
    assert "SEVERE_WARNING_PRESENT" in _codes(result)


def test_strict_claim_audit_failure_makes_output_invalid(run_root: Path) -> None:
    run_dir = _make_run_dir(run_root, claim_passed=False)

    result = validate_output_dir(run_dir, strict=True)

    assert result.status == ValidationStatus.INVALID
    assert "CLAIM_AUDIT_FAILED" in _codes(result)


def test_invalid_action_enum_fails(run_root: Path) -> None:
    run_dir = _make_run_dir(run_root, recommendation=_recommendation(action="strong_buy"))

    result = validate_output_dir(run_dir, strict=True)

    assert result.status == ValidationStatus.INVALID
    assert "INVALID_ACTION" in _codes(result)


def test_proposal_without_not_executed_fails(run_root: Path) -> None:
    run_dir = _make_run_dir(run_root, not_executed=None)

    result = validate_output_dir(run_dir, strict=True)

    assert result.status == ValidationStatus.INVALID
    assert "NOT_EXECUTED_FLAG_MISSING" in _codes(result)


def test_live_recommendation_with_unverified_strategy_fails(run_root: Path) -> None:
    run_dir = _make_run_dir(run_root, mode="live_recommendation", not_executed=None, strategy_verified=False)

    result = validate_output_dir(run_dir, strict=True)

    assert result.status == ValidationStatus.INVALID
    assert "LIVE_RECOMMENDATION_STRATEGY_UNVERIFIED" in _codes(result)


def test_source_hash_resolution_failure_invalid(run_root: Path) -> None:
    run_dir = _make_run_dir(run_root, recommendation=_recommendation(source_hashes=["missing"]))

    result = validate_output_dir(run_dir, strict=True)

    assert result.status == ValidationStatus.INVALID
    assert "SOURCE_HASH_UNRESOLVED" in _codes(result)


def test_broker_execution_artifact_invalid(run_root: Path) -> None:
    run_dir = _make_run_dir(run_root)
    (run_dir / "broker_order_ticket.json").write_text("{}", encoding="utf-8")

    result = validate_output_dir(run_dir, strict=True)

    assert result.status == ValidationStatus.INVALID
    assert "BROKER_EXECUTION_ARTIFACT_FORBIDDEN" in _codes(result)


def test_cli_strict_invalid_output_returns_nonzero(run_root: Path) -> None:
    run_dir = _make_run_dir(run_root, claim_passed=False)
    script = ROOT / "scripts" / "autopm_validate_output.py"

    result = subprocess.run(
        [sys.executable, str(script), "--run-dir", str(run_dir), "--strict"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "INVALID" in result.stdout


def test_no_network_access_required(run_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = _make_run_dir(run_root)

    def blocked_socket(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", blocked_socket)

    assert validate_output_dir(run_dir, strict=True).status == ValidationStatus.VALID


def test_no_broker_or_execution_imports() -> None:
    offenders: list[str] = []
    for path in [SRC / "ai_pm_agent" / "autopm" / "claim_audit.py", SRC / "ai_pm_agent" / "autopm" / "output_validator.py"]:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip().lower()
            if stripped.startswith(("import ", "from ")) and any(term in stripped for term in ("broker", "ibkr", "execution")):
                offenders.append(f"{path}:{line}")

    assert offenders == []
