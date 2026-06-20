from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.autopm.asia_ai_hardware import rank_asia_ai_hardware, score_asia_ai_hardware_candidate
from ai_pm_agent.autopm.stock_picker import TOP_PICK


FIXTURE_PATH = ROOT / "tests" / "fixtures" / "autopm_asia_ai_hardware_benchmark" / "benchmark_cases_v01.json"


def _fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _cases() -> list[dict[str, object]]:
    return _fixture()["rows"]  # type: ignore[return-value]


def test_benchmark_fixture_has_required_case_coverage() -> None:
    tickers = {row["ticker"] for row in _cases()}

    assert len(tickers) >= 15
    assert {
        "CCLTOP",
        "PCBWIN",
        "PPOEARLY",
        "OPTIPK",
        "CONNHI",
        "COOL",
        "ASIC",
        "MATURE",
        "STORY",
        "WCBAD",
        "NOVAL",
        "STALE",
    }.issubset(tickers)


def test_expected_score_ranges_and_required_labels_hold() -> None:
    for row in _cases():
        result = score_asia_ai_hardware_candidate(row)
        if row.get("expected_min_score") is not None:
            assert result.total_score >= float(row["expected_min_score"]), result.ticker
        if row.get("expected_max_score") is not None:
            assert result.total_score <= float(row["expected_max_score"]), result.ticker
        for warning in row.get("expected_required_warnings", []):
            assert warning in result.risk_warnings, result.ticker
        for reason_code in row.get("expected_required_reason_codes", []):
            assert reason_code in result.reason_codes, result.ticker


def test_top_tier_overlap_meets_expected_threshold() -> None:
    fixture = _fixture()
    expected_top = {row["ticker"] for row in _cases() if row.get("expected_tier") == TOP_PICK}
    actual_top = {row.ticker for row in rank_asia_ai_hardware(_cases()) if row.tier == TOP_PICK}

    overlap = len(expected_top.intersection(actual_top)) / len(expected_top)
    assert overlap >= float(fixture["top_tier_overlap_threshold"])


def test_expected_blocked_cases_do_not_enter_top_tier() -> None:
    blocked_expected = {
        row["ticker"]
        for row in _cases()
        if row.get("expected_required_warnings")
        and {"STORY_ONLY_AI_CLAIM", "MISSING_VALUATION", "STALE_MARKET_DATA"}.intersection(
            set(row["expected_required_warnings"])
        )
    }
    actual_top = {row.ticker for row in rank_asia_ai_hardware(_cases()) if row.tier == TOP_PICK}

    assert blocked_expected.isdisjoint(actual_top)


def test_story_only_company_cannot_become_strategy_top_tier() -> None:
    story = score_asia_ai_hardware_candidate(next(row for row in _cases() if row["ticker"] == "STORY"))

    assert story.tier != TOP_PICK
    assert "STORY_ONLY_AI_CLAIM" in story.risk_warnings


def test_missing_valuation_blocks_top_tier() -> None:
    missing = score_asia_ai_hardware_candidate(next(row for row in _cases() if row["ticker"] == "NOVAL"))

    assert missing.tier != TOP_PICK
    assert "MISSING_VALUATION" in missing.risk_warnings


def test_working_capital_deterioration_triggers_penalty() -> None:
    result = score_asia_ai_hardware_candidate(next(row for row in _cases() if row["ticker"] == "WCBAD"))

    assert "WORKING_CAPITAL_DETERIORATION" in result.risk_warnings
    assert result.factor_scores["gross_margin_fcf_quality_score"] < 0.5


def test_expensive_mature_leader_can_rank_quality_but_not_top_expected_return() -> None:
    ranking = rank_asia_ai_hardware(_cases())
    mature = next(row for row in ranking if row.ticker == "MATURE")
    leader = next(row for row in ranking if row.ticker == "CCLTOP")

    assert mature.factor_scores["bottleneck_score"] >= 0.85
    assert mature.factor_scores["valuation_expectation_gap_score"] < 0.3
    assert mature.total_score < leader.total_score
    assert mature.tier != TOP_PICK


def test_benchmark_ranking_is_deterministic() -> None:
    forward = [row.to_dict() for row in rank_asia_ai_hardware(_cases())]
    reverse = [row.to_dict() for row in rank_asia_ai_hardware(list(reversed(_cases())))]

    assert forward == reverse
