from __future__ import annotations

import json
import importlib.util
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ai_pm_agent_root_for_boundary_tests", ROOT / "ai_pm_agent.py")
assert SPEC is not None and SPEC.loader is not None
agent = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = agent
SPEC.loader.exec_module(agent)


FAKE_PORTFOLIO_CSV = """ticker,name,position_pct
TQQQ,ProShares UltraPro QQQ,12.5
SOXL,Direxion Daily Semiconductor Bull 3X Shares,8.0
"""


def _minimal_decision() -> dict:
    return {
        "ticker": "MSFT",
        "company_name": "Microsoft",
        "rating": "watch",
        "action": "watchlist",
        "suggested_position_pct": 0,
        "confidence_score": 5,
        "fundamental_quality_score": 5,
        "growth_visibility_score": 5,
        "valuation_attractiveness_score": 5,
        "ai_beneficiary_score": 5,
        "competitive_position_score": 5,
        "risk_score": 5,
        "evidence_quality_score": 5,
        "thesis_summary": "Standalone test thesis.",
        "ai_agent_demand_link": "Standalone test link.",
        "valuation_premium_reason": "Standalone test valuation.",
        "valuation_is_justified": False,
        "valuation_view": "Standalone valuation view.",
        "portfolio_fit": "Portfolio data disabled for recommendation path.",
        "bull_case": "Bull case.",
        "base_case": "Base case.",
        "bear_case": "Bear case.",
        "key_bull_points": ["Bull"],
        "key_bear_points": ["Bear"],
        "key_tracking_indicators": ["Indicator"],
        "thesis_kill_triggers": ["Trigger"],
        "data_gaps": ["Gap"],
        "deepest_questions": ["Question"],
        "price_review_threshold_pct": None,
        "thesis_review_triggers": [],
        "automatic_sell_rule": "none",
        "price_data_reliability": "high",
        "valuation_reliability": "medium",
        "manual_price_verification_required": False,
        "price_sanity_warnings": [],
        "price_verification_note": "",
        "final_pm_judgment": "Standalone judgment.",
    }


def test_build_pm_prompt_does_not_include_portfolio_context() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        portfolio_path = tmp_path / "portfolio.csv"
        portfolio_path.write_text(FAKE_PORTFOLIO_CSV, encoding="utf-8")

        legacy_diagnostics = agent.read_portfolio(str(portfolio_path))
        assert "## Current Portfolio" in legacy_diagnostics
        assert "TQQQ" in legacy_diagnostics

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
            evidence_quality={},
            cached_facts_md="facts",
            chokepoint_context_md="chokepoint",
            chokepoint_decision={},
            valuation_bridge_md="valuation",
            ai_agent_framework="framework",
        )

        assert "Current Portfolio" not in prompt
        assert "Current portfolio" not in prompt
        assert "TQQQ" not in prompt
        assert "SOXL" not in prompt
        assert "position_pct" not in prompt


def test_run_company_research_never_passes_portfolio_to_deep_pm_prompt(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        portfolio_path = tmp_path / "portfolio.csv"
        portfolio_path.write_text(FAKE_PORTFOLIO_CSV, encoding="utf-8")
        output_root = tmp_path / "outputs"

        deep_pm_prompts: list[str] = []

        monkeypatch.setattr(agent, "REUSE_TODAY_OUTPUTS", False)
        monkeypatch.setattr(agent, "FACT_CACHE_ENABLED", False)
        monkeypatch.setattr(agent, "CHOKEPOINT_SCOUT_ENABLED", False)
        monkeypatch.setattr(agent, "today_str", lambda: "2026-06-08")
        monkeypatch.setattr(agent, "now_str", lambda: "120000")
        monkeypatch.setattr(agent, "read_portfolio", lambda path: (_ for _ in ()).throw(AssertionError("read_portfolio must not be used by PM path")))
        monkeypatch.setattr(
            agent,
            "get_market_snapshot",
            lambda ticker: {
                "ticker": ticker,
                "data_fetch_diagnostics": [],
                "data_fetch_warnings": [],
                "market_data_reliability": "high",
                "financial_statement_reliability": "high",
                "price_data_reliability_from_fetch": "high",
            },
        )
        monkeypatch.setattr(agent, "snapshot_to_markdown", lambda snapshot: "snapshot")
        monkeypatch.setattr(agent, "build_price_sanity_check", lambda snapshot: {})
        monkeypatch.setattr(agent, "price_sanity_to_markdown", lambda price_sanity: "price sanity")
        monkeypatch.setattr(agent, "build_data_quality_warnings", lambda snapshot: [])
        monkeypatch.setattr(agent, "warnings_to_markdown", lambda title, warnings: f"## {title}\nNone")
        monkeypatch.setattr(agent, "build_industry_valuation_bridge", lambda snapshot, theme, peer_context_text: {})
        monkeypatch.setattr(agent, "valuation_bridge_to_markdown", lambda bridge: "valuation")
        monkeypatch.setattr(agent, "get_macro_snapshot", lambda: "macro")
        monkeypatch.setattr(agent, "build_peer_context", lambda ticker, name, theme, market, watchlist_path: "peers")
        monkeypatch.setattr(agent, "load_cached_facts", lambda ticker: [])
        monkeypatch.setattr(agent, "build_fact_cache_report", lambda ticker, name, theme, market: {})
        monkeypatch.setattr(agent, "get_evidence_context", lambda ticker, name, theme, market, query_type_filter=None: "evidence")
        monkeypatch.setattr(agent, "parse_evidence_search_diagnostics", lambda evidence_md: {})
        monkeypatch.setattr(agent, "score_evidence_quality_from_text", lambda evidence_md: {"evidence_search_diagnostics": {"evidence_search_diagnostics_summary": {}}})
        monkeypatch.setattr(agent, "merge_evidence_quality_with_cached_facts", lambda quality, cached_facts: quality)
        monkeypatch.setattr(agent, "fact_cache_report_to_markdown", lambda report: "fact report")
        monkeypatch.setattr(agent, "facts_to_markdown", lambda title, facts: "cached facts")
        monkeypatch.setattr(agent, "run_chokepoint_scout", lambda **kwargs: ("chokepoint", {}))
        monkeypatch.setattr(
            agent,
            "fetch_diagnostics_summary",
            lambda diagnostics: {
                "total": 0,
                "success": 0,
                "empty": 0,
                "failed": 0,
                "rate_limited": 0,
                "timeout": 0,
                "high_impact_failures": 0,
            },
        )
        monkeypatch.setattr(agent, "repair_json_object", lambda raw, schema_hint="", diagnostics=None: _minimal_decision())
        monkeypatch.setattr(agent, "repair_decision_schema", lambda decision, ticker, name, pm_memo, diagnostics=None: decision)
        monkeypatch.setattr(agent, "apply_chokepoint_weighted_overlay", lambda decision, *args, **kwargs: decision)
        monkeypatch.setattr(agent, "apply_pm_guardrails", lambda decision, *args, **kwargs: decision)
        monkeypatch.setattr(agent, "normalize_action_position_consistency", lambda decision: decision)
        monkeypatch.setattr(agent, "build_guardrailed_decision_appendix", lambda decision: "guardrail appendix")
        monkeypatch.setattr(agent, "build_quality_report", lambda *args, **kwargs: "quality report")
        monkeypatch.setattr(agent, "flatten_decision_for_summary", lambda row: {})
        monkeypatch.setattr(agent, "classify_summary_quality", lambda row: {})

        def fake_call_llm(agent_name: str, prompt: str, *args, **kwargs) -> str:
            if agent_name == "Deep PM Agent":
                deep_pm_prompts.append(prompt)
                return "PM memo without portfolio holdings."
            if agent_name == "Structured JSON Agent":
                return json.dumps(_minimal_decision())
            return ""

        monkeypatch.setattr(agent, "call_llm", fake_call_llm)

        row = agent.run_company_research(
            ticker="MSFT",
            name="Microsoft",
            theme="AI Supply Chain",
            market="US",
            portfolio_path=str(portfolio_path),
            output_root=str(output_root),
            watchlist_path=str(tmp_path / "watchlist.csv"),
        )

        assert len(deep_pm_prompts) == 1
        deep_pm_prompt = deep_pm_prompts[0]
        assert "Current Portfolio" not in deep_pm_prompt
        assert "Current portfolio" not in deep_pm_prompt
        assert "TQQQ" not in deep_pm_prompt
        assert "SOXL" not in deep_pm_prompt
        assert "position_pct" not in deep_pm_prompt

        output_dir = Path(row["output_dir"])
        prompt_artifact = (output_dir / "memo_prompt.md").read_text(encoding="utf-8")
        portfolio_artifact = (output_dir / "portfolio_context.md").read_text(encoding="utf-8")
        full_package = (output_dir / "full_research_package.md").read_text(encoding="utf-8")

        assert agent.PORTFOLIO_RECOMMENDATION_BOUNDARY_NOTICE in portfolio_artifact
        for artifact in [prompt_artifact, portfolio_artifact, full_package]:
            assert "TQQQ" not in artifact
            assert "SOXL" not in artifact
            assert "ProShares UltraPro QQQ" not in artifact
            assert "Direxion Daily Semiconductor Bull 3X Shares" not in artifact
