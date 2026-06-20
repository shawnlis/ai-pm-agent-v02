"""Asia AI Hardware stock picker strategy.

This strategy plugin is deterministic and ranking-only. It does not produce PM
instructions, sizing fields, rebalance rows, live data calls, or broker calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ai_pm_agent.autopm.models import AUTOPM_SCHEMA_VERSION, StockPickerScore
from ai_pm_agent.autopm.stock_picker import BLOCKED, CANDIDATE, TOP_PICK, WATCHLIST


class AsiaAIHardwareSubsector(StrEnum):
    CCL_M8_M9 = "CCL_M8_M9"
    PPO_HVLP_GLASS_CLOTH = "PPO_HVLP_GLASS_CLOTH"
    AI_PCB_SWITCH_BOARD = "AI_PCB_SWITCH_BOARD"
    OPTICS_PACKAGING_CONNECTOR = "OPTICS_PACKAGING_CONNECTOR"
    LIQUID_COOLING_POWER = "LIQUID_COOLING_POWER"
    ODM_AI_SERVER = "ODM_AI_SERVER"
    CLOUD_ASIC_DESIGN_SERVICE = "CLOUD_ASIC_DESIGN_SERVICE"
    HIGH_SPEED_CONNECTOR_COPPER = "HIGH_SPEED_CONNECTOR_COPPER"
    ADVANCED_PACKAGING_SUBSTRATE = "ADVANCED_PACKAGING_SUBSTRATE"


class CertificationStage(StrEnum):
    NONE = "none"
    SAMPLE = "sample"
    QUALIFICATION = "qualification"
    SMALL_BATCH = "small_batch"
    VOLUME_PRODUCTION = "volume_production"
    MATERIAL_REVENUE = "material_revenue"


FACTOR_WEIGHTS = {
    "bottleneck_score": 0.30,
    "ai_revenue_migration_score": 0.25,
    "customer_certification_order_visibility_score": 0.20,
    "gross_margin_fcf_quality_score": 0.15,
    "valuation_expectation_gap_score": 0.10,
}

SUBSECTOR_BOTTLENECK_SCORES = {
    AsiaAIHardwareSubsector.CCL_M8_M9.value: 0.92,
    AsiaAIHardwareSubsector.PPO_HVLP_GLASS_CLOTH.value: 0.75,
    AsiaAIHardwareSubsector.AI_PCB_SWITCH_BOARD.value: 0.9,
    AsiaAIHardwareSubsector.OPTICS_PACKAGING_CONNECTOR.value: 0.82,
    AsiaAIHardwareSubsector.LIQUID_COOLING_POWER.value: 0.72,
    AsiaAIHardwareSubsector.ODM_AI_SERVER.value: 0.62,
    AsiaAIHardwareSubsector.CLOUD_ASIC_DESIGN_SERVICE.value: 0.7,
    AsiaAIHardwareSubsector.HIGH_SPEED_CONNECTOR_COPPER.value: 0.86,
    AsiaAIHardwareSubsector.ADVANCED_PACKAGING_SUBSTRATE.value: 0.84,
}

STAGE_SCORES = {
    CertificationStage.NONE.value: 0.0,
    CertificationStage.SAMPLE.value: 0.2,
    CertificationStage.QUALIFICATION.value: 0.42,
    CertificationStage.SMALL_BATCH.value: 0.58,
    CertificationStage.VOLUME_PRODUCTION.value: 0.74,
    CertificationStage.MATERIAL_REVENUE.value: 0.95,
}

VALUATION_SCORES = {
    "attractive": 0.9,
    "reasonable": 0.78,
    "fair": 0.65,
    "stretched": 0.38,
    "expensive": 0.22,
    "missing": 0.0,
}

TOP_TIER_BLOCKERS = {
    "STORY_ONLY_AI_CLAIM",
    "MISSING_VALUATION",
    "STALE_MARKET_DATA",
    "SAMPLE_IS_NOT_QUALIFICATION",
    "QUALIFICATION_IS_NOT_VOLUME_PRODUCTION",
    "VOLUME_PRODUCTION_NOT_MATERIAL_REVENUE",
}


@dataclass(frozen=True)
class AsiaAIHardwareInput:
    ticker: str
    company_name: str
    market: str
    subsector: str
    source_hashes: tuple[str, ...]
    source_refs: tuple[str, ...]
    ai_revenue_share_pct: float | None = None
    ai_revenue_share_slope_pct: float | None = None
    certification_stage: str = CertificationStage.NONE.value
    material_revenue_evidence: bool = False
    order_visibility_quarters: float = 0.0
    high_end_capacity_expansion: bool = False
    gross_margin_trend_bps: float = 0.0
    fcf_conversion_pct: float = 0.0
    contract_liabilities_growth_pct: float = 0.0
    inventory_growth_pct: float = 0.0
    receivables_growth_pct: float = 0.0
    revenue_growth_pct: float = 0.0
    asp_trend_pct: float = 0.0
    eps_revision_pct: float = 0.0
    price_move_pct: float = 0.0
    valuation_label: str = "missing"
    customer_concentration_risk: float = 0.0
    second_source_risk: float = 0.0
    evidence_quality_score: float = 1.0
    market_data_stale: bool = False
    story_only_ai_claim: bool = False
    expected_tier: str = ""
    expected_min_score: float | None = None
    expected_max_score: float | None = None
    expected_required_warnings: tuple[str, ...] = ()
    expected_required_reason_codes: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> "AsiaAIHardwareInput":
        return cls(
            ticker=_text(row.get("ticker")),
            company_name=_text(row.get("company_name")),
            market=_text(row.get("market")),
            subsector=_text(row.get("subsector")),
            source_hashes=_string_tuple(row.get("source_hashes")),
            source_refs=_string_tuple(row.get("source_refs")),
            ai_revenue_share_pct=_optional_float(row.get("ai_revenue_share_pct")),
            ai_revenue_share_slope_pct=_optional_float(row.get("ai_revenue_share_slope_pct")),
            certification_stage=_text(row.get("certification_stage")) or CertificationStage.NONE.value,
            material_revenue_evidence=_bool(row.get("material_revenue_evidence")),
            order_visibility_quarters=_float(row.get("order_visibility_quarters")),
            high_end_capacity_expansion=_bool(row.get("high_end_capacity_expansion")),
            gross_margin_trend_bps=_float(row.get("gross_margin_trend_bps")),
            fcf_conversion_pct=_float(row.get("fcf_conversion_pct")),
            contract_liabilities_growth_pct=_float(row.get("contract_liabilities_growth_pct")),
            inventory_growth_pct=_float(row.get("inventory_growth_pct")),
            receivables_growth_pct=_float(row.get("receivables_growth_pct")),
            revenue_growth_pct=_float(row.get("revenue_growth_pct")),
            asp_trend_pct=_float(row.get("asp_trend_pct")),
            eps_revision_pct=_float(row.get("eps_revision_pct")),
            price_move_pct=_float(row.get("price_move_pct")),
            valuation_label=(_text(row.get("valuation_label")) or "missing").lower(),
            customer_concentration_risk=_float(row.get("customer_concentration_risk")),
            second_source_risk=_float(row.get("second_source_risk")),
            evidence_quality_score=_float(row.get("evidence_quality_score"), default=1.0),
            market_data_stale=_bool(row.get("market_data_stale")),
            story_only_ai_claim=_bool(row.get("story_only_ai_claim")),
            expected_tier=_text(row.get("expected_tier")),
            expected_min_score=_optional_float(row.get("expected_min_score")),
            expected_max_score=_optional_float(row.get("expected_max_score")),
            expected_required_warnings=_string_tuple(row.get("expected_required_warnings")),
            expected_required_reason_codes=_string_tuple(row.get("expected_required_reason_codes")),
        )


@dataclass(frozen=True)
class AsiaAIHardwareStockPickerScore:
    ticker: str
    company_name: str
    market: str
    subsector: str
    rank: int
    total_score: float
    tier: str
    factor_scores: dict[str, float] = field(default_factory=dict)
    leading_indicators: dict[str, object] = field(default_factory=dict)
    reason_codes: tuple[str, ...] = ()
    risk_warnings: tuple[str, ...] = ()
    data_gaps: tuple[str, ...] = ()
    red_flags: tuple[str, ...] = ()
    thesis_validation_triggers: tuple[str, ...] = ()
    thesis_kill_triggers: tuple[str, ...] = ()
    downgrade_triggers: tuple[str, ...] = ()
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

    def to_dict(self) -> dict[str, object]:
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "market": self.market,
            "subsector": self.subsector,
            "rank": self.rank,
            "total_score": self.total_score,
            "tier": self.tier,
            "factor_scores": dict(self.factor_scores),
            "leading_indicators": dict(self.leading_indicators),
            "reason_codes": list(self.reason_codes),
            "risk_warnings": list(self.risk_warnings),
            "data_gaps": list(self.data_gaps),
            "red_flags": list(self.red_flags),
            "thesis_validation_triggers": list(self.thesis_validation_triggers),
            "thesis_kill_triggers": list(self.thesis_kill_triggers),
            "downgrade_triggers": list(self.downgrade_triggers),
            "required_next_evidence": list(self.required_next_evidence),
            "source_hashes": list(self.source_hashes),
            "source_refs": list(self.source_refs),
            "not_recommendation_until_recommender": self.not_recommendation_until_recommender,
            "schema_version": self.schema_version,
        }


def score_asia_ai_hardware_candidate(
    candidate: AsiaAIHardwareInput | dict[str, Any],
    *,
    rank: int = 0,
) -> AsiaAIHardwareStockPickerScore:
    row = candidate if isinstance(candidate, AsiaAIHardwareInput) else AsiaAIHardwareInput.from_mapping(candidate)
    factor_scores = {
        "bottleneck_score": _bottleneck_score(row),
        "ai_revenue_migration_score": _ai_revenue_migration_score(row),
        "customer_certification_order_visibility_score": _customer_visibility_score(row),
        "gross_margin_fcf_quality_score": _margin_fcf_quality_score(row),
        "valuation_expectation_gap_score": _valuation_gap_score(row),
    }
    reason_codes, risk_warnings, data_gaps, red_flags, required_next_evidence = _diagnostics(row, factor_scores)
    total_score = _weighted_total(factor_scores, risk_warnings)
    tier = _tier(total_score, risk_warnings)
    return AsiaAIHardwareStockPickerScore(
        ticker=row.ticker,
        company_name=row.company_name,
        market=row.market,
        subsector=row.subsector,
        rank=rank,
        total_score=round(total_score, 4),
        tier=tier,
        factor_scores=factor_scores,
        leading_indicators=_leading_indicators(row),
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        risk_warnings=tuple(dict.fromkeys(risk_warnings)),
        data_gaps=tuple(dict.fromkeys(data_gaps)),
        red_flags=tuple(dict.fromkeys(red_flags)),
        thesis_validation_triggers=_thesis_validation_triggers(row),
        thesis_kill_triggers=_thesis_kill_triggers(row),
        downgrade_triggers=_downgrade_triggers(row),
        required_next_evidence=tuple(dict.fromkeys(required_next_evidence)),
        source_hashes=row.source_hashes,
        source_refs=row.source_refs,
    )


def rank_asia_ai_hardware(candidates: list[AsiaAIHardwareInput | dict[str, Any]]) -> list[AsiaAIHardwareStockPickerScore]:
    unranked = [score_asia_ai_hardware_candidate(candidate) for candidate in candidates]
    ordered = sorted(unranked, key=lambda item: (-item.total_score, item.ticker))
    return [
        AsiaAIHardwareStockPickerScore(
            ticker=item.ticker,
            company_name=item.company_name,
            market=item.market,
            subsector=item.subsector,
            rank=index,
            total_score=item.total_score,
            tier=item.tier,
            factor_scores=item.factor_scores,
            leading_indicators=item.leading_indicators,
            reason_codes=item.reason_codes,
            risk_warnings=item.risk_warnings,
            data_gaps=item.data_gaps,
            red_flags=item.red_flags,
            thesis_validation_triggers=item.thesis_validation_triggers,
            thesis_kill_triggers=item.thesis_kill_triggers,
            downgrade_triggers=item.downgrade_triggers,
            required_next_evidence=item.required_next_evidence,
            source_hashes=item.source_hashes,
            source_refs=item.source_refs,
            not_recommendation_until_recommender=item.not_recommendation_until_recommender,
            schema_version=item.schema_version,
        )
        for index, item in enumerate(ordered, start=1)
    ]


def _bottleneck_score(row: AsiaAIHardwareInput) -> float:
    base = SUBSECTOR_BOTTLENECK_SCORES.get(row.subsector, 0.35)
    if row.high_end_capacity_expansion:
        base += 0.04
    risk_penalty = 0.08 * _clamp(row.second_source_risk) + 0.04 * _clamp(row.customer_concentration_risk)
    return _clamp(base - risk_penalty)


def _ai_revenue_migration_score(row: AsiaAIHardwareInput) -> float:
    if row.story_only_ai_claim or row.ai_revenue_share_pct is None:
        return 0.08
    share_score = _clamp(row.ai_revenue_share_pct / 50.0)
    slope_score = _clamp((row.ai_revenue_share_slope_pct or 0.0) / 20.0)
    score = 0.65 * share_score + 0.35 * slope_score
    if row.evidence_quality_score < 0.55:
        return min(score, 0.35)
    return _clamp(score)


def _customer_visibility_score(row: AsiaAIHardwareInput) -> float:
    stage_score = STAGE_SCORES.get(row.certification_stage, 0.0)
    visibility_score = _clamp(row.order_visibility_quarters / 6.0)
    capacity_score = 0.1 if row.high_end_capacity_expansion else 0.0
    score = 0.58 * stage_score + 0.32 * visibility_score + capacity_score
    if row.certification_stage == CertificationStage.VOLUME_PRODUCTION.value and not row.material_revenue_evidence:
        score = min(score, 0.62)
    return _clamp(score)


def _margin_fcf_quality_score(row: AsiaAIHardwareInput) -> float:
    margin_score = _clamp((row.gross_margin_trend_bps + 300.0) / 600.0)
    fcf_score = _clamp(row.fcf_conversion_pct / 90.0)
    prepayment_score = _clamp(row.contract_liabilities_growth_pct / 50.0)
    asp_score = _clamp((row.asp_trend_pct + 10.0) / 25.0)
    working_capital_penalty = _working_capital_penalty(row)
    return _clamp((0.35 * margin_score) + (0.35 * fcf_score) + (0.15 * prepayment_score) + (0.15 * asp_score) - working_capital_penalty)


def _valuation_gap_score(row: AsiaAIHardwareInput) -> float:
    if row.market_data_stale:
        return 0.0
    score = VALUATION_SCORES.get(row.valuation_label, 0.0)
    if _price_move_outpaces_revision(row):
        score -= 0.18
    return _clamp(score)


def _weighted_total(scores: dict[str, float], warnings: tuple[str, ...] | list[str]) -> float:
    total = sum(scores[name] * FACTOR_WEIGHTS[name] for name in FACTOR_WEIGHTS)
    if "WORKING_CAPITAL_DETERIORATION" in warnings:
        total -= 0.06
    if "PRICE_MOVE_OUTPACES_EPS_REVISION" in warnings:
        total -= 0.05
    if "CUSTOMER_CONCENTRATION_RISK" in warnings:
        total -= 0.03
    if "SECOND_SOURCE_RISK" in warnings:
        total -= 0.03
    return _clamp(total)


def _tier(score: float, warnings: tuple[str, ...] | list[str]) -> str:
    warning_set = set(warnings)
    if warning_set.intersection(TOP_TIER_BLOCKERS):
        return WATCHLIST if score >= 0.4 else BLOCKED
    if "WORKING_CAPITAL_DETERIORATION" in warning_set and score < 0.72:
        return CANDIDATE
    if score >= 0.74:
        return TOP_PICK
    if score >= 0.56:
        return CANDIDATE
    if score >= 0.35:
        return WATCHLIST
    return BLOCKED


def _diagnostics(
    row: AsiaAIHardwareInput,
    factor_scores: dict[str, float],
) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    reason_codes: list[str] = []
    risk_warnings: list[str] = []
    data_gaps: list[str] = []
    red_flags: list[str] = []
    required_next_evidence: list[str] = []

    if not row.source_hashes or not row.source_refs:
        data_gaps.append("SOURCE_METADATA_MISSING")
        required_next_evidence.append("source metadata for strategy reasons")
    if row.story_only_ai_claim:
        risk_warnings.append("STORY_ONLY_AI_CLAIM")
        data_gaps.append("AI_REVENUE_EVIDENCE_MISSING")
        required_next_evidence.append("quantified AI revenue evidence")
    elif factor_scores["ai_revenue_migration_score"] >= 0.55:
        reason_codes.append("AI_REVENUE_MIGRATION_EVIDENCED")

    if row.certification_stage == CertificationStage.SAMPLE.value:
        risk_warnings.append("SAMPLE_IS_NOT_QUALIFICATION")
        required_next_evidence.append("customer qualification evidence")
    if row.certification_stage == CertificationStage.QUALIFICATION.value:
        risk_warnings.append("QUALIFICATION_IS_NOT_VOLUME_PRODUCTION")
        required_next_evidence.append("volume production evidence")
    if row.certification_stage == CertificationStage.VOLUME_PRODUCTION.value and not row.material_revenue_evidence:
        risk_warnings.append("VOLUME_PRODUCTION_NOT_MATERIAL_REVENUE")
        required_next_evidence.append("material revenue evidence")
    if row.certification_stage == CertificationStage.MATERIAL_REVENUE.value:
        reason_codes.append("MATERIAL_REVENUE_EVIDENCED")

    if row.valuation_label == "missing":
        risk_warnings.append("MISSING_VALUATION")
        data_gaps.append("VALUATION_DATA_MISSING")
        required_next_evidence.append("valuation evidence")
    if row.market_data_stale:
        risk_warnings.append("STALE_MARKET_DATA")
        data_gaps.append("FRESH_MARKET_DATA_REQUIRED")
        required_next_evidence.append("fresh market data")
    if _working_capital_penalty(row) >= 0.12:
        risk_warnings.append("WORKING_CAPITAL_DETERIORATION")
        red_flags.append("inventory or receivables growth exceeds revenue growth")
    if _price_move_outpaces_revision(row):
        risk_warnings.append("PRICE_MOVE_OUTPACES_EPS_REVISION")
        red_flags.append("price move outpaces earnings revision")
    if row.customer_concentration_risk >= 0.65:
        risk_warnings.append("CUSTOMER_CONCENTRATION_RISK")
    if row.second_source_risk >= 0.65:
        risk_warnings.append("SECOND_SOURCE_RISK")
    if factor_scores["bottleneck_score"] >= 0.75:
        reason_codes.append("BOTTLENECK_SUBSECTOR_EXPOSURE")
    if factor_scores["customer_certification_order_visibility_score"] >= 0.65:
        reason_codes.append("CUSTOMER_VISIBILITY_EVIDENCED")
    if factor_scores["gross_margin_fcf_quality_score"] >= 0.65:
        reason_codes.append("MARGIN_FCF_QUALITY_EVIDENCED")
    if factor_scores["valuation_expectation_gap_score"] >= 0.65:
        reason_codes.append("VALUATION_EXPECTATION_GAP_REASONABLE")

    return reason_codes, risk_warnings, data_gaps, red_flags, required_next_evidence


def _leading_indicators(row: AsiaAIHardwareInput) -> dict[str, object]:
    return {
        "ai_revenue_share_pct": row.ai_revenue_share_pct,
        "ai_revenue_share_slope_pct": row.ai_revenue_share_slope_pct,
        "certification_stage": row.certification_stage,
        "material_revenue_evidence": row.material_revenue_evidence,
        "order_visibility_quarters": row.order_visibility_quarters,
        "high_end_capacity_expansion": row.high_end_capacity_expansion,
        "gross_margin_trend_bps": row.gross_margin_trend_bps,
        "fcf_conversion_pct": row.fcf_conversion_pct,
        "contract_liabilities_growth_pct": row.contract_liabilities_growth_pct,
        "inventory_growth_pct": row.inventory_growth_pct,
        "receivables_growth_pct": row.receivables_growth_pct,
        "revenue_growth_pct": row.revenue_growth_pct,
        "asp_trend_pct": row.asp_trend_pct,
        "eps_revision_pct": row.eps_revision_pct,
        "price_move_pct": row.price_move_pct,
        "valuation_label": row.valuation_label,
        "customer_concentration_risk": row.customer_concentration_risk,
        "second_source_risk": row.second_source_risk,
    }


def _thesis_validation_triggers(row: AsiaAIHardwareInput) -> tuple[str, ...]:
    triggers = [
        "AI revenue share continues rising with source-backed evidence",
        "customer stage advances with explicit evidence",
        "margin and FCF quality remain supported by working-capital data",
    ]
    if row.certification_stage != CertificationStage.MATERIAL_REVENUE.value:
        triggers.append("material revenue evidence arrives")
    return tuple(triggers)


def _thesis_kill_triggers(row: AsiaAIHardwareInput) -> tuple[str, ...]:
    return (
        "AI revenue evidence fails to progress beyond current stage",
        "inventory or receivables growth stays materially above revenue growth",
        "valuation becomes stretched without earnings revision support",
        "customer concentration or second-source risk rises materially",
    )


def _downgrade_triggers(row: AsiaAIHardwareInput) -> tuple[str, ...]:
    triggers = [
        "market data becomes stale",
        "valuation evidence becomes missing or stretched",
        "gross margin or FCF conversion deteriorates",
    ]
    if row.customer_concentration_risk >= 0.5:
        triggers.append("customer concentration risk increases")
    return tuple(triggers)


def _working_capital_penalty(row: AsiaAIHardwareInput) -> float:
    inventory_spread = row.inventory_growth_pct - row.revenue_growth_pct
    receivables_spread = row.receivables_growth_pct - row.revenue_growth_pct
    return _clamp(max(inventory_spread, 0.0) / 80.0 + max(receivables_spread, 0.0) / 80.0)


def _price_move_outpaces_revision(row: AsiaAIHardwareInput) -> bool:
    return row.price_move_pct >= 35.0 and row.price_move_pct - row.eps_revision_pct >= 25.0


def _text(value: Any) -> str:
    return str(value or "").strip()


def _string_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, tuple):
        return tuple(_text(item) for item in value if _text(item))
    if isinstance(value, list):
        return tuple(_text(item) for item in value if _text(item))
    return tuple(part.strip() for part in _text(value).replace(";", ",").split(",") if part.strip())


def _optional_float(value: Any) -> float | None:
    if _text(value) == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y"}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
