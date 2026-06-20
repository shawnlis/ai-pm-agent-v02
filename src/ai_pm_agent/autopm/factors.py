"""Deterministic generic stock picker factor scoring.

This module is ranking-only. It does not create PM instructions, size
positions, read portfolio context, call live providers, or contact brokers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


FACTOR_NAMES = (
    "business_quality_score",
    "growth_quality_score",
    "earnings_revision_score",
    "valuation_attractiveness_score",
    "momentum_technical_score",
    "balance_sheet_quality_score",
    "evidence_quality_score",
    "catalyst_score",
    "accounting_risk_penalty",
    "crowding_priced_in_risk",
)

POSITIVE_FACTOR_NAMES = FACTOR_NAMES[:8]
PENALTY_FACTOR_NAMES = FACTOR_NAMES[8:]

WEAK_EVIDENCE_CAP = 0.55
MISSING_VALUATION_TOP_PICK_BLOCKER = "VALUATION_DATA_MISSING"
STALE_MARKET_DATA_BLOCKER = "STALE_MARKET_DATA"
ACCOUNTING_RISK_BLOCKER = "ACCOUNTING_RISK_BLOCKS_TOP_TIER"
PRICED_IN_PENALTY_REASON = "PRICE_MOVE_OUTPACES_EPS_REVISION"
SOURCE_METADATA_GAP = "SOURCE_METADATA_MISSING"


@dataclass(frozen=True)
class FactorScoreResult:
    factor_scores: dict[str, float]
    raw_score: float
    capped_score: float
    reason_codes: tuple[str, ...] = ()
    data_gaps: tuple[str, ...] = ()
    red_flags: tuple[str, ...] = ()
    required_next_evidence: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    source_hashes: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class FactorInput:
    ticker: str
    company_name: str
    market: str
    scores: dict[str, float] = field(default_factory=dict)
    source_hashes: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    evidence_reliability: float = 1.0
    valuation_present: bool = True
    market_data_stale: bool = False
    accounting_red_flags: tuple[str, ...] = ()
    price_move_pct: float | None = None
    eps_revision_pct: float | None = None

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> "FactorInput":
        scores = {name: _float(row.get(name)) for name in POSITIVE_FACTOR_NAMES}
        scores.update({name: _float(row.get(name)) for name in PENALTY_FACTOR_NAMES})
        return cls(
            ticker=_text(row.get("ticker")),
            company_name=_text(row.get("company_name")),
            market=_text(row.get("market")),
            scores=scores,
            source_hashes=_string_tuple(row.get("source_hashes")),
            source_refs=_string_tuple(row.get("source_refs")),
            evidence_reliability=_float(row.get("evidence_reliability"), default=1.0),
            valuation_present=_bool(row.get("valuation_present"), default=True),
            market_data_stale=_bool(row.get("market_data_stale")),
            accounting_red_flags=_string_tuple(row.get("accounting_red_flags")),
            price_move_pct=_optional_float(row.get("price_move_pct")),
            eps_revision_pct=_optional_float(row.get("eps_revision_pct")),
        )


def compute_factor_scores(inputs: FactorInput | dict[str, Any]) -> FactorScoreResult:
    """Score one stock candidate with deterministic, fixture-friendly rules."""

    candidate = inputs if isinstance(inputs, FactorInput) else FactorInput.from_mapping(inputs)
    factor_scores = _normalized_scores(candidate)
    reason_codes: list[str] = []
    data_gaps: list[str] = []
    red_flags: list[str] = []
    required_next_evidence: list[str] = []
    blockers: list[str] = []

    if not candidate.source_hashes or not candidate.source_refs:
        data_gaps.append(SOURCE_METADATA_GAP)
        required_next_evidence.append("source metadata for ranking reasons")

    if candidate.evidence_reliability < 0.6 or factor_scores["evidence_quality_score"] < 0.6:
        reason_codes.append("WEAK_EVIDENCE_SCORE_CAP")
        required_next_evidence.append("stronger primary or official evidence")

    if not candidate.valuation_present:
        reason_codes.append(MISSING_VALUATION_TOP_PICK_BLOCKER)
        data_gaps.append(MISSING_VALUATION_TOP_PICK_BLOCKER)
        required_next_evidence.append("valuation snapshot")
        blockers.append(MISSING_VALUATION_TOP_PICK_BLOCKER)
        factor_scores["valuation_attractiveness_score"] = 0.0

    if candidate.market_data_stale:
        reason_codes.append(STALE_MARKET_DATA_BLOCKER)
        data_gaps.append(STALE_MARKET_DATA_BLOCKER)
        required_next_evidence.append("fresh market snapshot")
        blockers.append(STALE_MARKET_DATA_BLOCKER)
        factor_scores["valuation_attractiveness_score"] = 0.0
        factor_scores["momentum_technical_score"] = 0.0

    if candidate.accounting_red_flags or factor_scores["accounting_risk_penalty"] >= 0.7:
        reason_codes.append(ACCOUNTING_RISK_BLOCKER)
        red_flags.extend(candidate.accounting_red_flags or ("accounting risk penalty",))
        blockers.append(ACCOUNTING_RISK_BLOCKER)

    if _price_move_outpaces_revision(candidate):
        factor_scores["crowding_priced_in_risk"] = max(factor_scores["crowding_priced_in_risk"], 0.7)
        reason_codes.append(PRICED_IN_PENALTY_REASON)
        red_flags.append("price move outpaces earnings revision")

    raw_score = _weighted_score(factor_scores)
    capped_score = raw_score
    if "WEAK_EVIDENCE_SCORE_CAP" in reason_codes:
        capped_score = min(capped_score, WEAK_EVIDENCE_CAP)

    return FactorScoreResult(
        factor_scores=factor_scores,
        raw_score=round(raw_score, 4),
        capped_score=round(capped_score, 4),
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        data_gaps=tuple(dict.fromkeys(data_gaps)),
        red_flags=tuple(dict.fromkeys(red_flags)),
        required_next_evidence=tuple(dict.fromkeys(required_next_evidence)),
        blockers=tuple(dict.fromkeys(blockers)),
        source_hashes=candidate.source_hashes,
        source_refs=candidate.source_refs,
    )


def _normalized_scores(candidate: FactorInput) -> dict[str, float]:
    return {name: _clamp(candidate.scores.get(name, 0.0)) for name in FACTOR_NAMES}


def _weighted_score(scores: dict[str, float]) -> float:
    positive = sum(scores[name] for name in POSITIVE_FACTOR_NAMES) / len(POSITIVE_FACTOR_NAMES)
    penalty = (
        0.7 * scores["accounting_risk_penalty"]
        + 0.3 * scores["crowding_priced_in_risk"]
    )
    return _clamp(positive - (0.35 * penalty))


def _price_move_outpaces_revision(candidate: FactorInput) -> bool:
    if candidate.price_move_pct is None or candidate.eps_revision_pct is None:
        return False
    return candidate.price_move_pct >= 35.0 and candidate.price_move_pct - candidate.eps_revision_pct >= 25.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any, *, default: float = 0.0) -> float:
    try:
        return _clamp(float(value))
    except (TypeError, ValueError):
        return default


def _optional_float(value: Any) -> float | None:
    if _text(value) == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "y"}


def _string_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, tuple):
        return tuple(_text(item) for item in value if _text(item))
    if isinstance(value, list):
        return tuple(_text(item) for item in value if _text(item))
    return tuple(part.strip() for part in _text(value).replace(";", ",").split(",") if part.strip())
