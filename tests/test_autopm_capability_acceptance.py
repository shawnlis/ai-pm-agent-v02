from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.autopm.models import RecommendationAction
from ai_pm_agent.autopm.policy import default_policy


FIXTURE_DIR = ROOT / "tests" / "fixtures" / "autopm_capability"
BUY_ADD = {RecommendationAction.BUY.value, RecommendationAction.ADD.value}
RECOMMENDATION_LIKE = BUY_ADD | {
    RecommendationAction.HOLD.value,
    RecommendationAction.TRIM.value,
    RecommendationAction.SELL.value,
    RecommendationAction.WATCH.value,
    RecommendationAction.MANUAL_REVIEW.value,
}
REQUIRED_FRAMEWORK_CAPABILITIES = {
    "business_model",
    "unit_economics",
    "growth_quality",
    "moat_competition",
    "industry_cycle",
    "financial_quality",
    "capital_structure",
    "management_governance",
    "market_expectation_gap",
    "technical_flow_signals",
    "valuation",
    "thesis_kill_triggers",
    "portfolio_fit",
    "asia_ai_hardware_bottleneck_score",
    "ai_revenue_migration",
    "customer_certification_order_visibility",
    "gross_margin_fcf_quality",
    "valuation_expectation_gap",
}


def _load_json(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _cases() -> list[dict[str, Any]]:
    return _load_json("capability_cases_v01.json")["cases"]


def _case(case_id: str) -> dict[str, Any]:
    for item in _cases():
        if item["case_id"] == case_id:
            return item
    raise AssertionError(f"case missing: {case_id}")


def _source_hashes(case: dict[str, Any]) -> set[str]:
    return {source["source_hash"] for source in case["source_manifest"]}


def _assert_source_backed_reason_code(case: dict[str, Any], reason: dict[str, Any]) -> None:
    assert reason["backing_type"] in {"source", "policy"}
    if reason["backing_type"] == "source":
        assert reason["source_hash"] in _source_hashes(case)
        assert reason["evidence_level"]
        assert reason["period"]
        assert reason["source_date"]
        assert reason["field"]
    else:
        assert reason["policy_rule"]


def test_acceptance_matrix_covers_full_user_framework() -> None:
    matrix = _load_json("acceptance_matrix_v01.json")
    capabilities = {item["capability"] for item in matrix["capabilities"]}

    assert matrix["schema_version"] == "autopm_capability_acceptance.v0.1"
    assert REQUIRED_FRAMEWORK_CAPABILITIES <= capabilities
    for item in matrix["capabilities"]:
        assert item["required_fields"]
        assert item["acceptance_standard"]


def test_fixture_pack_contains_required_scenarios() -> None:
    expected_case_ids = {
        "high_quality_ai_bottleneck",
        "story_only_ai_claim",
        "sample_stage_company",
        "qualification_stage_company",
        "volume_without_material_revenue",
        "missing_valuation_company",
        "stale_market_data_company",
        "working_capital_deterioration",
        "portfolio_concentration_block",
        "overweight_existing_holding",
        "thesis_broken_holding",
    }

    cases = _cases()

    assert {case["case_id"] for case in cases} == expected_case_ids
    for case in cases:
        assert case["expected_action"] in {action.value for action in RecommendationAction}
        assert case["source_manifest"]
        assert case["reason_codes"]


def test_every_buy_add_expected_outcome_requires_source_backed_reason_codes() -> None:
    buy_add_cases = [case for case in _cases() if case["expected_action"] in BUY_ADD]

    assert buy_add_cases
    for case in buy_add_cases:
        assert case["reason_codes"]
        assert any(reason["backing_type"] == "source" for reason in case["reason_codes"])
        for reason in case["reason_codes"]:
            _assert_source_backed_reason_code(case, reason)


def test_missing_valuation_blocks_buy_add() -> None:
    case = _case("missing_valuation_company")

    assert case["missing_valuation"] is True
    assert case["expected_action"] not in BUY_ADD
    assert not case["gates"]["valuation"]
    assert "VALUATION_DATA_MISSING" in case["risk_warnings"]
    assert set(case["forbidden_actions"]) >= BUY_ADD


def test_stale_market_data_blocks_valuation_dependent_buy_add() -> None:
    case = _case("stale_market_data_company")

    assert case["valuation_dependent"] is True
    assert case["market_data_stale"] is True
    assert case["expected_action"] not in BUY_ADD
    assert not case["gates"]["valuation"]
    assert "STALE_MARKET_DATA" in case["risk_warnings"]


def test_story_only_ai_claims_cannot_rank_top_pick() -> None:
    case = _case("story_only_ai_claim")

    assert case["expected_tier"] != "top_pick"
    assert case["expected_action"] not in BUY_ADD
    assert not case["gates"]["evidence"]
    assert "WEAK_EVIDENCE" in case["risk_warnings"]


def test_sample_does_not_equal_qualification() -> None:
    case = _case("sample_stage_company")

    assert case["certification_stage"] == "sample"
    assert case["certification_stage"] != "qualification"
    assert case["expected_action"] not in BUY_ADD
    assert "SAMPLE_NOT_QUALIFICATION" in case["risk_warnings"]


def test_qualification_does_not_equal_volume_production() -> None:
    case = _case("qualification_stage_company")

    assert case["certification_stage"] == "qualification"
    assert case["certification_stage"] != "volume_production"
    assert case["expected_action"] not in BUY_ADD
    assert "QUALIFICATION_NOT_VOLUME_PRODUCTION" in case["risk_warnings"]


def test_volume_production_does_not_equal_material_revenue_without_evidence() -> None:
    case = _case("volume_without_material_revenue")

    assert case["certification_stage"] == "volume_production"
    assert case["material_revenue_evidence"] is False
    assert case["expected_action"] not in BUY_ADD
    assert "MATERIAL_REVENUE_EVIDENCE_MISSING" in case["risk_warnings"]


def test_working_capital_deterioration_triggers_risk_penalty() -> None:
    case = _case("working_capital_deterioration")
    outputs = case["capability_outputs"]

    assert case["working_capital_deterioration"] is True
    assert not case["gates"]["risk"]
    assert "WORKING_CAPITAL_DETERIORATION" in case["risk_warnings"]
    assert outputs["financial_quality_score"] < 0.5
    assert outputs["gross_margin_fcf_quality_score"] < 0.5
    assert outputs["working_capital_warnings"]


def test_price_move_outpacing_eps_revision_triggers_priced_in_penalty() -> None:
    penalized_cases = [case for case in _cases() if case["priced_in_penalty"]]

    assert penalized_cases
    for case in penalized_cases:
        assert case["price_move_pct"] > case["eps_revision_pct"]
        assert "PRICE_MOVE_OUTPACES_EPS_REVISION" in case["risk_warnings"]


def test_portfolio_concentration_blocks_add() -> None:
    case = _case("portfolio_concentration_block")

    assert case["portfolio_concentration_breach"] is True
    assert case["expected_action"] != RecommendationAction.ADD.value
    assert RecommendationAction.ADD.value in case["forbidden_actions"]
    assert not case["gates"]["portfolio"]
    assert "THEME_EXPOSURE_LIMIT_EXCEEDED" in case["risk_warnings"]


def test_target_weight_pct_respects_policy_caps() -> None:
    policy = default_policy()

    for case in _cases():
        assert case["target_weight_pct"] <= case["max_position_pct"]
        assert case["target_weight_pct"] <= policy.max_single_name_weight_pct
        if case["expected_action"] == RecommendationAction.TRIM.value:
            assert case["current_weight_pct"] > case["target_weight_pct"]


def test_every_buy_add_expected_outcome_has_thesis_kill_triggers() -> None:
    buy_add_cases = [case for case in _cases() if case["expected_action"] in BUY_ADD]

    assert buy_add_cases
    for case in buy_add_cases:
        assert len(case["thesis_kill_triggers"]) >= 3


def test_every_recommendation_like_output_has_next_evidence_or_no_gap_flag() -> None:
    for case in _cases():
        if case["expected_action"] in RECOMMENDATION_LIKE:
            assert case["required_next_evidence"] or case["no_gap_flag"] is True


def test_source_hashes_resolve_for_all_source_backed_reason_codes() -> None:
    for case in _cases():
        for reason in case["reason_codes"]:
            _assert_source_backed_reason_code(case, reason)


def test_fixture_outputs_include_required_machine_checkable_fields() -> None:
    matrix = _load_json("acceptance_matrix_v01.json")
    required_fields = {
        field
        for capability in matrix["capabilities"]
        for field in capability["required_fields"]
        if field
        not in {"reason_codes", "thesis_kill_triggers", "target_weight_pct", "max_position_pct", "valuation_gate"}
    }

    for case in _cases():
        outputs = case["capability_outputs"]
        missing = sorted(field for field in required_fields if field not in outputs and field not in case)
        assert missing == [], f"{case['case_id']} missing {missing}"
        assert "valuation" in case["gates"]
