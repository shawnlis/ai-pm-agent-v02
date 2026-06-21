"""Portfolio-aware autopm recommendation generation.

This module is explicit autopm-only logic. It does not import legacy PM prompt
builders, does not read live providers, and does not create execution orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from ai_pm_agent.autopm.claim_audit import audit_recommendation_claims
from ai_pm_agent.autopm.models import (
    AUTOPM_SCHEMA_VERSION,
    EvidenceGateResult,
    PortfolioAwareRecommendation,
    PortfolioGateResult,
    RecommendationAction,
    RedTeamResult,
    RiskGateResult,
    StockPickerScore,
    ValuationGateResult,
)
from ai_pm_agent.autopm.policy import AutopmPolicy, default_policy
from ai_pm_agent.autopm.portfolio_policy import AutopmPortfolioPolicy
from ai_pm_agent.autopm.sizing import SizingInputs, size_position


@dataclass(frozen=True)
class SourceReference:
    code: str
    source_hash: str
    evidence_level: str
    source_date: str
    period: str
    field: str

    def to_reason_code(self) -> dict[str, str]:
        return {
            "code": self.code,
            "backing_type": "source",
            "source_hash": self.source_hash,
            "evidence_level": self.evidence_level,
            "source_date": self.source_date,
            "period": self.period,
            "field": self.field,
        }


@dataclass(frozen=True)
class AutopmRecommendation:
    ticker: str
    company_name: str
    market: str
    action: RecommendationAction
    rating: str
    conviction_score: float
    current_weight_pct: float
    target_weight_pct: float
    delta_weight_pct: float
    max_position_pct: float
    evidence_score: float
    valuation_score: float
    quality_score: float
    momentum_score: float
    risk_score: float
    portfolio_fit_score: float
    reason_codes: tuple[dict[str, str], ...] = ()
    risk_warnings: tuple[str, ...] = ()
    evidence_summary: str = ""
    valuation_summary: str = ""
    portfolio_fit_summary: str = ""
    thesis_kill_triggers: tuple[str, ...] = ()
    required_next_evidence: tuple[str, ...] = ()
    next_review_date: str = ""
    source_hashes: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    gate_results: dict[str, dict[str, object]] = field(default_factory=dict)
    claim_audit_passed: bool = False
    schema_version: str = AUTOPM_SCHEMA_VERSION

    def to_portfolio_aware_recommendation(self) -> PortfolioAwareRecommendation:
        return PortfolioAwareRecommendation(
            ticker=self.ticker,
            company_name=self.company_name,
            market=self.market,
            action=self.action,
            rating=self.rating,
            conviction_score=self.conviction_score,
            current_weight_pct=self.current_weight_pct,
            target_weight_pct=self.target_weight_pct,
            delta_weight_pct=self.delta_weight_pct,
            max_position_pct=self.max_position_pct,
            evidence_score=self.evidence_score,
            valuation_score=self.valuation_score,
            quality_score=self.quality_score,
            momentum_score=self.momentum_score,
            risk_score=self.risk_score,
            portfolio_fit_score=self.portfolio_fit_score,
            reason_codes=tuple(reason["code"] for reason in self.reason_codes),
            risk_warnings=self.risk_warnings,
            thesis_kill_triggers=self.thesis_kill_triggers,
            required_next_evidence=self.required_next_evidence,
        )

    def to_audit_row(self) -> dict[str, object]:
        return {
            "ticker": self.ticker,
            "action": self.action.value,
            "conviction_score": self.conviction_score,
            "current_weight_pct": self.current_weight_pct,
            "target_weight_pct": self.target_weight_pct,
            "delta_weight_pct": self.delta_weight_pct,
            "max_position_pct": self.max_position_pct,
            "valuation_dependent": True,
            "valuation_gate": self.gate_results.get("valuation_gate", {}),
            "valuation_snapshot_present": self.valuation_score > 0,
            "portfolio_gate": self.gate_results.get("portfolio_gate", {}),
            "thesis_kill_triggers": list(self.thesis_kill_triggers),
            "risk_warnings": list(self.risk_warnings),
            "red_team_warnings": list(self.gate_results.get("red_team", {}).get("warning_codes", [])),
            "reason_codes": [dict(reason) for reason in self.reason_codes],
        }

    def to_dict(self) -> dict[str, object]:
        payload = self.to_audit_row()
        payload.update(
            {
                "company_name": self.company_name,
                "market": self.market,
                "rating": self.rating,
                "evidence_score": self.evidence_score,
                "valuation_score": self.valuation_score,
                "quality_score": self.quality_score,
                "momentum_score": self.momentum_score,
                "risk_score": self.risk_score,
                "portfolio_fit_score": self.portfolio_fit_score,
                "evidence_summary": self.evidence_summary,
                "valuation_summary": self.valuation_summary,
                "portfolio_fit_summary": self.portfolio_fit_summary,
                "required_next_evidence": list(self.required_next_evidence),
                "next_review_date": self.next_review_date,
                "source_hashes": list(self.source_hashes),
                "source_refs": list(self.source_refs),
                "gate_results": self.gate_results,
                "claim_audit_passed": self.claim_audit_passed,
                "schema_version": self.schema_version,
            }
        )
        return payload


def recommend_from_score(
    score: StockPickerScore,
    *,
    current_weight_pct: float,
    portfolio_gate: PortfolioGateResult,
    evidence_gate: EvidenceGateResult,
    valuation_gate: ValuationGateResult,
    risk_gate: RiskGateResult,
    red_team: RedTeamResult,
    source_refs: tuple[SourceReference, ...],
    source_manifest: dict[str, object],
    policy: AutopmPortfolioPolicy | AutopmPolicy | None = None,
    market_data_stale: bool = False,
    today: date | None = None,
) -> AutopmRecommendation:
    policy_obj = policy or AutopmPortfolioPolicy()
    sizing = size_position(
        SizingInputs(
            score=score,
            current_weight_pct=current_weight_pct,
            portfolio_gate=portfolio_gate,
            evidence_gate=evidence_gate,
            valuation_gate=valuation_gate,
            risk_gate=risk_gate,
            red_team=red_team,
            policy=policy_obj,
            market_data_stale=market_data_stale,
        )
    )
    action = _action(score, sizing.blocked_by, sizing.decision.current_weight_pct, sizing.decision.target_weight_pct, _base_policy(policy_obj))
    recommendation = _build_recommendation(
        score,
        sizing=sizing,
        action=action,
        evidence_gate=evidence_gate,
        valuation_gate=valuation_gate,
        risk_gate=risk_gate,
        portfolio_gate=portfolio_gate,
        red_team=red_team,
        source_refs=source_refs,
        today=today or date.today(),
    )
    audit = audit_recommendation_claims([recommendation.to_audit_row()], source_manifest, policy=_base_policy(policy_obj))
    if audit.passed:
        return _replace_claim_audit(recommendation, True)
    downgraded = _manual_review_copy(recommendation, tuple(issue.code for issue in audit.issues))
    audit_after = audit_recommendation_claims([downgraded.to_audit_row()], source_manifest, policy=_base_policy(policy_obj))
    return _replace_claim_audit(downgraded, audit_after.passed)


def _build_recommendation(
    score: StockPickerScore,
    *,
    sizing,
    action: RecommendationAction,
    evidence_gate: EvidenceGateResult,
    valuation_gate: ValuationGateResult,
    risk_gate: RiskGateResult,
    portfolio_gate: PortfolioGateResult,
    red_team: RedTeamResult,
    source_refs: tuple[SourceReference, ...],
    today: date,
) -> AutopmRecommendation:
    factor_scores = score.factor_scores
    return AutopmRecommendation(
        ticker=score.ticker,
        company_name=score.company_name,
        market=score.market,
        action=action,
        rating=score.tier,
        conviction_score=round(score.score, 4),
        current_weight_pct=sizing.decision.current_weight_pct,
        target_weight_pct=sizing.decision.target_weight_pct,
        delta_weight_pct=sizing.decision.delta_weight_pct,
        max_position_pct=sizing.decision.max_position_pct,
        evidence_score=evidence_gate.score,
        valuation_score=valuation_gate.score,
        quality_score=_quality_score(factor_scores),
        momentum_score=float(factor_scores.get("momentum_technical_score", 0.0)),
        risk_score=risk_gate.score,
        portfolio_fit_score=portfolio_gate.portfolio_fit_score,
        reason_codes=tuple(ref.to_reason_code() for ref in source_refs),
        risk_warnings=tuple(dict.fromkeys(sizing.risk_warnings + sizing.blocked_by + portfolio_gate.concentration_warnings + risk_gate.risk_warnings + red_team.warning_codes)),
        evidence_summary="Evidence gate passed." if evidence_gate.passed else "Evidence gate failed or requires review.",
        valuation_summary=valuation_gate.valuation_basis or ("Valuation gate passed." if valuation_gate.passed else "Valuation gate failed."),
        portfolio_fit_summary="Portfolio gate passed." if portfolio_gate.passed else "Portfolio gate failed; add-style action blocked.",
        thesis_kill_triggers=red_team.thesis_kill_triggers,
        required_next_evidence=tuple(dict.fromkeys(score.required_next_evidence + evidence_gate.required_next_evidence + red_team.missing_evidence)),
        next_review_date=(today + timedelta(days=30)).isoformat(),
        source_hashes=tuple(ref.source_hash for ref in source_refs),
        source_refs=tuple(ref.field for ref in source_refs),
        gate_results={
            "evidence_gate": {"passed": evidence_gate.passed, "score": evidence_gate.score},
            "valuation_gate": {"passed": valuation_gate.passed, "score": valuation_gate.score},
            "portfolio_gate": {"passed": portfolio_gate.passed, "score": portfolio_gate.portfolio_fit_score},
            "risk_gate": {"passed": risk_gate.passed, "score": risk_gate.score},
            "red_team": {"passed": red_team.passed, "warning_codes": list(red_team.warning_codes)},
        },
    )


def _action(
    score: StockPickerScore,
    blocked_by: tuple[str, ...],
    current_weight: float,
    target_weight: float,
    policy: AutopmPolicy,
) -> RecommendationAction:
    if blocked_by:
        if "RED_TEAM_FAILED" in blocked_by or "SEVERE_RED_TEAM_WARNING" in blocked_by:
            if policy.sell_allowed and current_weight > 0 and target_weight == 0:
                return RecommendationAction.SELL
            return RecommendationAction.MANUAL_REVIEW
        if {"VALUATION_GATE_FAILED", "STALE_MARKET_DATA", "EVIDENCE_GATE_FAILED"}.intersection(blocked_by):
            return RecommendationAction.WATCH if current_weight == 0 else RecommendationAction.MANUAL_REVIEW
        if "PORTFOLIO_GATE_FAILED" in blocked_by:
            return RecommendationAction.HOLD if current_weight > 0 else RecommendationAction.MANUAL_REVIEW
        return RecommendationAction.MANUAL_REVIEW
    if target_weight == 0:
        return RecommendationAction.AVOID
    if current_weight == 0 and target_weight > 0:
        return RecommendationAction.BUY
    if target_weight > current_weight:
        return RecommendationAction.ADD
    if current_weight - target_weight >= policy.trim_threshold_pct:
        return RecommendationAction.TRIM if policy.sell_allowed else RecommendationAction.HOLD
    return RecommendationAction.HOLD


def _manual_review_copy(recommendation: AutopmRecommendation, warnings: tuple[str, ...]) -> AutopmRecommendation:
    return AutopmRecommendation(
        ticker=recommendation.ticker,
        company_name=recommendation.company_name,
        market=recommendation.market,
        action=RecommendationAction.MANUAL_REVIEW,
        rating=recommendation.rating,
        conviction_score=recommendation.conviction_score,
        current_weight_pct=recommendation.current_weight_pct,
        target_weight_pct=recommendation.current_weight_pct,
        delta_weight_pct=0.0,
        max_position_pct=recommendation.max_position_pct,
        evidence_score=recommendation.evidence_score,
        valuation_score=recommendation.valuation_score,
        quality_score=recommendation.quality_score,
        momentum_score=recommendation.momentum_score,
        risk_score=recommendation.risk_score,
        portfolio_fit_score=recommendation.portfolio_fit_score,
        reason_codes=recommendation.reason_codes,
        risk_warnings=tuple(dict.fromkeys(recommendation.risk_warnings + warnings)),
        evidence_summary=recommendation.evidence_summary,
        valuation_summary=recommendation.valuation_summary,
        portfolio_fit_summary=recommendation.portfolio_fit_summary,
        thesis_kill_triggers=recommendation.thesis_kill_triggers,
        required_next_evidence=recommendation.required_next_evidence,
        next_review_date=recommendation.next_review_date,
        source_hashes=recommendation.source_hashes,
        source_refs=recommendation.source_refs,
        gate_results=recommendation.gate_results,
    )


def _replace_claim_audit(recommendation: AutopmRecommendation, passed: bool) -> AutopmRecommendation:
    return AutopmRecommendation(**{**recommendation.__dict__, "claim_audit_passed": passed})


def _quality_score(factor_scores: dict[str, float]) -> float:
    keys = ("business_quality_score", "growth_quality_score", "balance_sheet_quality_score")
    values = [float(factor_scores[key]) for key in keys if key in factor_scores]
    return round(sum(values) / len(values), 4) if values else 0.0


def _base_policy(policy: AutopmPortfolioPolicy | AutopmPolicy) -> AutopmPolicy:
    if isinstance(policy, AutopmPortfolioPolicy):
        return policy.base_policy
    return policy
