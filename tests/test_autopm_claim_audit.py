from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.autopm.claim_audit import (
    audit_output_consistency,
    audit_policy_consistency,
    audit_recommendation_claims,
    audit_source_manifest_coverage,
)
from ai_pm_agent.autopm.policy import default_policy


SOURCE_HASH = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _source_manifest(*, stale: bool = False) -> dict:
    return {
        "sources": [
            {
                "source_hash": SOURCE_HASH,
                "source_date": "2026-03-31",
                "period": "2026Q1",
                "evidence_level": "primary_official",
                "stale": stale,
                "warning_codes": [],
            }
        ]
    }


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


def _codes(result) -> set[str]:
    return {issue.code for issue in result.issues}


def test_source_backed_recommendation_passes_claim_audit() -> None:
    result = audit_recommendation_claims([_recommendation()], _source_manifest(), policy=default_policy())

    assert result.passed is True
    assert result.issues == []


def test_missing_source_hash_fails() -> None:
    rec = _recommendation(
        reason_codes=[
            {
                "code": "AI_REVENUE_MIGRATION_CONFIRMED",
                "backing_type": "source",
                "evidence_level": "primary_official",
                "source_date": "2026-03-31",
                "period": "2026Q1",
                "field": "ai_revenue_share",
            }
        ]
    )

    result = audit_source_manifest_coverage([rec], _source_manifest())

    assert result.passed is False
    assert "SOURCE_HASH_MISSING" in _codes(result)


def test_unknown_source_hash_fails() -> None:
    rec = _recommendation(
        reason_codes=[
            {
                "code": "AI_REVENUE_MIGRATION_CONFIRMED",
                "backing_type": "source",
                "source_hash": "missing",
                "evidence_level": "primary_official",
                "source_date": "2026-03-31",
                "period": "2026Q1",
                "field": "ai_revenue_share",
            }
        ]
    )

    result = audit_source_manifest_coverage([rec], _source_manifest())

    assert result.passed is False
    assert "SOURCE_HASH_UNKNOWN" in _codes(result)


def test_stale_source_blocks_high_conviction() -> None:
    result = audit_source_manifest_coverage([_recommendation(conviction_score=0.9)], _source_manifest(stale=True))

    assert result.passed is False
    assert "STALE_EVIDENCE_HIGH_CONVICTION" in _codes(result)


def test_policy_inconsistency_fails() -> None:
    result = audit_policy_consistency([_recommendation(portfolio_gate={"passed": False})], policy=default_policy())

    assert result.passed is False
    assert "PORTFOLIO_GATE_FAILED_BUY_ADD" in _codes(result)


def test_target_weight_over_cap_fails() -> None:
    result = audit_policy_consistency([_recommendation(target_weight_pct=6.0, delta_weight_pct=6.0)], policy=default_policy())

    assert result.passed is False
    assert "TARGET_WEIGHT_OVER_CAP" in _codes(result)


def test_delta_mismatch_fails() -> None:
    result = audit_policy_consistency([_recommendation(delta_weight_pct=1.0)], policy=default_policy())

    assert result.passed is False
    assert "DELTA_WEIGHT_MISMATCH" in _codes(result)


def test_valuation_dependent_recommendation_requires_valuation_snapshot_or_gate() -> None:
    rec = _recommendation(valuation_gate={"passed": False}, valuation_snapshot_present=False)

    result = audit_policy_consistency([rec], policy=default_policy())

    assert result.passed is False
    assert {"VALUATION_GATE_FAILED_BUY_ADD", "VALUATION_SNAPSHOT_REQUIRED"} <= _codes(result)


def test_trade_style_action_requires_reason_codes() -> None:
    result = audit_output_consistency([_recommendation(reason_codes=[])])

    assert result.passed is False
    assert "REASON_CODES_MISSING" in _codes(result)


def test_severe_red_team_warning_forces_review_style_action() -> None:
    result = audit_policy_consistency(
        [_recommendation(action="buy", red_team_warnings=["SEVERE_THESIS_BREAK"])],
        policy=default_policy(),
    )

    assert result.passed is False
    assert "SEVERE_RED_TEAM_ACTION_FORBIDDEN" in _codes(result)
