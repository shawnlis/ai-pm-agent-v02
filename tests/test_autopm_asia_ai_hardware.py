from __future__ import annotations

import json
from pathlib import Path
import socket
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.autopm.asia_ai_hardware import (
    AsiaAIHardwareSubsector,
    CertificationStage,
    FACTOR_WEIGHTS,
    TOP_TIER_BLOCKERS,
    rank_asia_ai_hardware,
    score_asia_ai_hardware_candidate,
)
from ai_pm_agent.autopm.stock_picker import TOP_PICK


FIXTURE_PATH = ROOT / "tests" / "fixtures" / "autopm_asia_ai_hardware_benchmark" / "benchmark_cases_v01.json"


def _fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _cases() -> list[dict[str, object]]:
    return _fixture()["rows"]  # type: ignore[return-value]


def _case(ticker: str) -> dict[str, object]:
    return next(row for row in _cases() if row["ticker"] == ticker)


def test_taxonomy_and_weights_are_stable() -> None:
    assert [item.value for item in AsiaAIHardwareSubsector] == [
        "CCL_M8_M9",
        "PPO_HVLP_GLASS_CLOTH",
        "AI_PCB_SWITCH_BOARD",
        "OPTICS_PACKAGING_CONNECTOR",
        "LIQUID_COOLING_POWER",
        "ODM_AI_SERVER",
        "CLOUD_ASIC_DESIGN_SERVICE",
        "HIGH_SPEED_CONNECTOR_COPPER",
        "ADVANCED_PACKAGING_SUBSTRATE",
    ]
    assert [item.value for item in CertificationStage] == [
        "none",
        "sample",
        "qualification",
        "small_batch",
        "volume_production",
        "material_revenue",
    ]
    assert FACTOR_WEIGHTS == {
        "bottleneck_score": 0.30,
        "ai_revenue_migration_score": 0.25,
        "customer_certification_order_visibility_score": 0.20,
        "gross_margin_fcf_quality_score": 0.15,
        "valuation_expectation_gap_score": 0.10,
    }


def test_material_bottleneck_ai_migration_reasonable_valuation_ranks_high() -> None:
    ranking = rank_asia_ai_hardware(_cases())

    assert ranking[0].ticker == "CCLTOP"
    assert ranking[0].tier == TOP_PICK
    assert ranking[0].total_score >= 0.78
    assert "BOTTLENECK_SUBSECTOR_EXPOSURE" in ranking[0].reason_codes
    assert "AI_REVENUE_MIGRATION_EVIDENCED" in ranking[0].reason_codes


def test_story_only_ai_claim_cannot_top_rank() -> None:
    result = score_asia_ai_hardware_candidate(_case("STORY"))

    assert result.tier != TOP_PICK
    assert "STORY_ONLY_AI_CLAIM" in result.risk_warnings
    assert "quantified AI revenue evidence" in result.required_next_evidence


def test_sample_does_not_equal_qualification() -> None:
    result = score_asia_ai_hardware_candidate(_case("SAMPLE"))

    assert result.tier != TOP_PICK
    assert "SAMPLE_IS_NOT_QUALIFICATION" in result.risk_warnings
    assert "customer qualification evidence" in result.required_next_evidence


def test_qualification_does_not_equal_volume_production() -> None:
    result = score_asia_ai_hardware_candidate(_case("QUAL"))

    assert result.tier != TOP_PICK
    assert "QUALIFICATION_IS_NOT_VOLUME_PRODUCTION" in result.risk_warnings
    assert "volume production evidence" in result.required_next_evidence


def test_volume_production_does_not_equal_material_revenue_without_evidence() -> None:
    result = score_asia_ai_hardware_candidate(_case("VOLNOMAT"))

    assert result.tier != TOP_PICK
    assert "VOLUME_PRODUCTION_NOT_MATERIAL_REVENUE" in result.risk_warnings
    assert "material revenue evidence" in result.required_next_evidence


def test_working_capital_deterioration_penalizes_quality() -> None:
    result = score_asia_ai_hardware_candidate(_case("WCBAD"))

    assert "WORKING_CAPITAL_DETERIORATION" in result.risk_warnings
    assert "inventory or receivables growth exceeds revenue growth" in result.red_flags
    assert result.factor_scores["gross_margin_fcf_quality_score"] < 0.5


def test_price_move_outpacing_eps_revision_penalizes_score() -> None:
    result = score_asia_ai_hardware_candidate(_case("PRICEY"))

    assert "PRICE_MOVE_OUTPACES_EPS_REVISION" in result.risk_warnings
    assert "price move outpaces earnings revision" in result.red_flags
    assert result.factor_scores["valuation_expectation_gap_score"] < 0.3


def test_missing_valuation_and_stale_market_data_block_top_tier() -> None:
    missing = score_asia_ai_hardware_candidate(_case("NOVAL"))
    stale = score_asia_ai_hardware_candidate(_case("STALE"))

    assert missing.tier != TOP_PICK
    assert stale.tier != TOP_PICK
    assert "MISSING_VALUATION" in missing.risk_warnings
    assert "STALE_MARKET_DATA" in stale.risk_warnings
    assert stale.factor_scores["valuation_expectation_gap_score"] == 0.0


def test_expensive_mature_leader_has_quality_but_lower_expected_upside() -> None:
    result = score_asia_ai_hardware_candidate(_case("MATURE"))
    top = score_asia_ai_hardware_candidate(_case("CCLTOP"))

    assert result.factor_scores["bottleneck_score"] >= 0.85
    assert "MATERIAL_REVENUE_EVIDENCED" in result.reason_codes
    assert result.factor_scores["valuation_expectation_gap_score"] < 0.3
    assert result.total_score < top.total_score
    assert result.tier != TOP_PICK


def test_output_is_ranking_only_and_has_no_portfolio_context() -> None:
    row = dict(_case("CCLTOP"))
    row["current" + "_weight_pct"] = 99.0
    output = score_asia_ai_hardware_candidate(row).to_dict()

    forbidden_fields = {
        "action",
        "target" + "_weight_pct",
        "current" + "_weight_pct",
        "delta" + "_weight_pct",
        "max_position" + "_pct",
    }
    assert forbidden_fields.isdisjoint(output)
    assert output["not_recommendation_until_recommender"] is True


def test_ranking_is_deterministic() -> None:
    first = [row.to_dict() for row in rank_asia_ai_hardware(_cases())]
    second = [row.to_dict() for row in rank_asia_ai_hardware(list(reversed(_cases())))]

    assert first == second


def test_top_tier_blocker_set_is_explicit() -> None:
    assert TOP_TIER_BLOCKERS == {
        "STORY_ONLY_AI_CLAIM",
        "MISSING_VALUATION",
        "STALE_MARKET_DATA",
        "SAMPLE_IS_NOT_QUALIFICATION",
        "QUALIFICATION_IS_NOT_VOLUME_PRODUCTION",
        "VOLUME_PRODUCTION_NOT_MATERIAL_REVENUE",
    }


def test_strategy_performs_no_network_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked_socket(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", blocked_socket)

    assert score_asia_ai_hardware_candidate(_case("CCLTOP")).ticker == "CCLTOP"


def test_no_autopm_module_imports_broker_or_execution_modules() -> None:
    autopm_root = Path("src/ai_pm_agent/autopm")
    forbidden_import_terms = ("broker", "ibkr", "execution")
    offenders: list[str] = []

    for path in autopm_root.glob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip().lower()
            if stripped.startswith(("import ", "from ")) and any(term in stripped for term in forbidden_import_terms):
                offenders.append(f"{path}:{line}")

    assert offenders == []
