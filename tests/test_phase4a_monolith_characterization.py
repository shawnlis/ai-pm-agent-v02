from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ai_pm_agent_root_for_phase4a_tests", ROOT / "ai_pm_agent.py")
assert SPEC is not None and SPEC.loader is not None
agent = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = agent
SPEC.loader.exec_module(agent)


def test_pm_prompt_builder_signature_keeps_portfolio_out_of_contract() -> None:
    signature = inspect.signature(agent.build_pm_prompt)
    assert list(signature.parameters) == [
        "ticker",
        "name",
        "theme",
        "market",
        "snapshot_md",
        "data_quality_md",
        "data_fetch_md",
        "price_sanity_md",
        "macro_md",
        "peer_md",
        "evidence_md",
        "evidence_quality",
        "cached_facts_md",
        "chokepoint_context_md",
        "chokepoint_decision",
        "valuation_bridge_md",
        "ai_agent_framework",
    ]
    forbidden_parameters = {"portfolio_md", "portfolio_context", "portfolio_path", "holdings", "positions"}
    assert forbidden_parameters.isdisjoint(signature.parameters)


def test_pm_prompt_boundary_instruction_is_stable_and_portfolio_free() -> None:
    prompt = agent.build_pm_prompt(
        ticker="MSFT",
        name="Microsoft",
        theme="AI Supply Chain",
        market="US",
        snapshot_md="snapshot",
        data_quality_md="quality",
        data_fetch_md="fetch",
        price_sanity_md="price sanity",
        macro_md="macro",
        peer_md="peers",
        evidence_md="evidence",
        evidence_quality={"evidence_quality_score": 5},
        cached_facts_md="facts",
        chokepoint_context_md="chokepoint",
        chokepoint_decision={"chokepoint_score": 0},
        valuation_bridge_md="valuation",
        ai_agent_framework="framework",
    )

    assert "L. Portfolio independence: no holdings are supplied" in prompt
    assert "do not infer overlap, concentration risk, duplicated beta, or suitability" in prompt
    assert "Current Portfolio" not in prompt
    assert "Current portfolio" not in prompt
    assert "portfolio_md" not in prompt
    assert "TQQQ" not in prompt
    assert "SOXL" not in prompt


def test_disabled_portfolio_context_notice_is_diagnostics_only() -> None:
    notice = agent.disabled_portfolio_context_notice()

    assert notice.startswith("## Portfolio Recommendation Boundary")
    assert agent.PORTFOLIO_RECOMMENDATION_BOUNDARY_NOTICE in notice
    assert "Legacy portfolio.csv input is not read" in notice
    assert "used in PM memo/recommendation logic" in notice
    assert "offline portfolio exposure runner" in notice
    assert "Current Portfolio" not in notice
    assert "TQQQ" not in notice
