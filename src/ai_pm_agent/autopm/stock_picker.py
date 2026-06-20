"""Generic deterministic stock picker ranking.

The stock picker produces universe ranking artifacts only. It intentionally
does not emit PM instructions, sizing fields, rebalance rows, broker calls, or
portfolio-aware outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ai_pm_agent.autopm.factors import (
    ACCOUNTING_RISK_BLOCKER,
    MISSING_VALUATION_TOP_PICK_BLOCKER,
    STALE_MARKET_DATA_BLOCKER,
    FactorInput,
    compute_factor_scores,
)
from ai_pm_agent.autopm.models import AUTOPM_SCHEMA_VERSION, StockPickerScore


TOP_PICK = "top_pick"
CANDIDATE = "candidate"
WATCHLIST = "watchlist"
AVOID = "avoid"
BLOCKED = "blocked"
TIERS = (TOP_PICK, CANDIDATE, WATCHLIST, AVOID, BLOCKED)


@dataclass(frozen=True)
class StockPickerRanking:
    ticker: str
    company_name: str
    market: str
    rank: int
    total_score: float
    tier: str
    factor_scores: dict[str, float] = field(default_factory=dict)
    reason_codes: tuple[str, ...] = ()
    data_gaps: tuple[str, ...] = ()
    red_flags: tuple[str, ...] = ()
    required_next_evidence: tuple[str, ...] = ()
    source_hashes: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    not_recommendation_until_recommender: bool = True
    schema_version: str = AUTOPM_SCHEMA_VERSION

    def to_stock_picker_score(self) -> StockPickerScore:
        return StockPickerScore(
            ticker=self.ticker,
            company_name=self.company_name,
            market=self.market,
            rank=self.rank,
            score=self.total_score,
            tier=self.tier,
            factor_scores=dict(self.factor_scores),
            reason_codes=self.reason_codes,
            data_gaps=self.data_gaps,
            red_flags=self.red_flags,
            required_next_evidence=self.required_next_evidence,
            schema_version=self.schema_version,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "market": self.market,
            "rank": self.rank,
            "total_score": self.total_score,
            "tier": self.tier,
            "factor_scores": dict(self.factor_scores),
            "reason_codes": list(self.reason_codes),
            "data_gaps": list(self.data_gaps),
            "red_flags": list(self.red_flags),
            "required_next_evidence": list(self.required_next_evidence),
            "source_hashes": list(self.source_hashes),
            "source_refs": list(self.source_refs),
            "not_recommendation_until_recommender": self.not_recommendation_until_recommender,
            "schema_version": self.schema_version,
        }


def score_stock(candidate: FactorInput | dict[str, Any], *, rank: int = 0) -> StockPickerRanking:
    """Score one candidate without portfolio context or live data."""

    inputs = candidate if isinstance(candidate, FactorInput) else FactorInput.from_mapping(candidate)
    result = compute_factor_scores(inputs)
    tier = _tier_for_score(result.capped_score, result.blockers)
    return StockPickerRanking(
        ticker=inputs.ticker,
        company_name=inputs.company_name,
        market=inputs.market,
        rank=rank,
        total_score=result.capped_score,
        tier=tier,
        factor_scores=result.factor_scores,
        reason_codes=result.reason_codes,
        data_gaps=result.data_gaps,
        red_flags=result.red_flags,
        required_next_evidence=result.required_next_evidence,
        source_hashes=result.source_hashes,
        source_refs=result.source_refs,
    )


def rank_stocks(candidates: list[FactorInput | dict[str, Any]]) -> list[StockPickerRanking]:
    """Return deterministic descending rankings for fixture/provider candidates."""

    unranked = [score_stock(candidate) for candidate in candidates]
    ordered = sorted(unranked, key=lambda item: (-item.total_score, item.ticker))
    return [
        StockPickerRanking(
            ticker=item.ticker,
            company_name=item.company_name,
            market=item.market,
            rank=index,
            total_score=item.total_score,
            tier=item.tier,
            factor_scores=item.factor_scores,
            reason_codes=item.reason_codes,
            data_gaps=item.data_gaps,
            red_flags=item.red_flags,
            required_next_evidence=item.required_next_evidence,
            source_hashes=item.source_hashes,
            source_refs=item.source_refs,
            not_recommendation_until_recommender=item.not_recommendation_until_recommender,
            schema_version=item.schema_version,
        )
        for index, item in enumerate(ordered, start=1)
    ]


def _tier_for_score(score: float, blockers: tuple[str, ...]) -> str:
    if ACCOUNTING_RISK_BLOCKER in blockers:
        return BLOCKED
    if score >= 0.75 and not _top_tier_blocked(blockers):
        return TOP_PICK
    if score >= 0.6:
        return CANDIDATE
    if score >= 0.4:
        return WATCHLIST
    if blockers:
        return BLOCKED
    return AVOID


def _top_tier_blocked(blockers: tuple[str, ...]) -> bool:
    return any(blocker in blockers for blocker in (MISSING_VALUATION_TOP_PICK_BLOCKER, STALE_MARKET_DATA_BLOCKER))
