"""Portfolio-aware constraints for autopm recommendations."""

from __future__ import annotations

from dataclasses import dataclass, field

from ai_pm_agent.autopm.models import PortfolioGateResult
from ai_pm_agent.autopm.policy import AutopmPolicy, default_policy
from ai_pm_agent.portfolio.exposure import calculate_base_leverage_adjusted_gross_exposure
from ai_pm_agent.portfolio.models import PortfolioSnapshot


@dataclass(frozen=True)
class CandidatePortfolioMetadata:
    ticker: str
    theme: str = ""
    region: str = ""
    sector: str = ""
    issuer: str = ""


@dataclass(frozen=True)
class AutopmPortfolioPolicy:
    base_policy: AutopmPolicy = field(default_factory=default_policy)
    max_sector_weight_pct: float = 35.0
    max_issuer_weight_pct: float = 7.5


@dataclass(frozen=True)
class PortfolioPolicyContext:
    ticker: str
    current_weight_pct: float
    cash_pct: float
    theme_exposure_pct: float
    region_exposure_pct: float
    sector_exposure_pct: float
    issuer_exposure_pct: float
    leverage_adjusted_exposure_pct: float
    concentration_warnings: tuple[str, ...] = ()


def compute_portfolio_policy_context(
    snapshot: PortfolioSnapshot,
    candidate: CandidatePortfolioMetadata,
    *,
    policy: AutopmPortfolioPolicy | None = None,
) -> PortfolioPolicyContext:
    policy_obj = policy or AutopmPortfolioPolicy()
    total = snapshot.total_base_equity_value
    current_weight_pct = _current_weight_pct(snapshot, candidate.ticker)
    cash_pct = 0.0 if total == 0 else snapshot.cash / total * 100.0
    theme = _exposure_pct(snapshot.theme_exposure, candidate.theme)
    region = _exposure_pct(snapshot.region_exposure, candidate.region)
    sector = _exposure_pct(snapshot.sector_exposure, candidate.sector)
    issuer = _exposure_pct(snapshot.issuer_exposure, candidate.issuer or candidate.ticker.upper())
    leverage = calculate_base_leverage_adjusted_gross_exposure(snapshot) * 100.0
    warnings = _concentration_warnings(policy_obj, current_weight_pct, theme, region, sector, issuer, leverage, cash_pct)
    return PortfolioPolicyContext(
        ticker=candidate.ticker.upper(),
        current_weight_pct=round(current_weight_pct, 4),
        cash_pct=round(cash_pct, 4),
        theme_exposure_pct=round(theme, 4),
        region_exposure_pct=round(region, 4),
        sector_exposure_pct=round(sector, 4),
        issuer_exposure_pct=round(issuer, 4),
        leverage_adjusted_exposure_pct=round(leverage, 4),
        concentration_warnings=warnings,
    )


def evaluate_portfolio_gate(
    snapshot: PortfolioSnapshot,
    candidate: CandidatePortfolioMetadata,
    *,
    proposed_target_weight_pct: float,
    policy: AutopmPortfolioPolicy | None = None,
) -> PortfolioGateResult:
    policy_obj = policy or AutopmPortfolioPolicy()
    base = policy_obj.base_policy
    context = compute_portfolio_policy_context(snapshot, candidate, policy=policy_obj)
    add_pct = max(0.0, proposed_target_weight_pct - context.current_weight_pct)
    warnings = list(context.concentration_warnings)
    reason_codes: list[str] = []

    if proposed_target_weight_pct > base.max_single_name_weight_pct:
        warnings.append("MAX_SINGLE_NAME_EXCEEDED")
    if context.current_weight_pct > 0.0 and add_pct > base.max_add_pct_per_run:
        warnings.append("MAX_ADD_PER_RUN_EXCEEDED")
    if context.current_weight_pct == 0.0 and proposed_target_weight_pct > base.max_new_position_pct:
        warnings.append("MAX_NEW_POSITION_EXCEEDED")
    if context.theme_exposure_pct + add_pct > base.max_theme_weight_pct:
        warnings.append("THEME_EXPOSURE_LIMIT_EXCEEDED")
    if context.region_exposure_pct + add_pct > base.max_region_weight_pct:
        warnings.append("REGION_EXPOSURE_LIMIT_EXCEEDED")
    if context.sector_exposure_pct + add_pct > policy_obj.max_sector_weight_pct:
        warnings.append("SECTOR_EXPOSURE_LIMIT_EXCEEDED")
    if context.issuer_exposure_pct + add_pct > policy_obj.max_issuer_weight_pct:
        warnings.append("ISSUER_EXPOSURE_LIMIT_EXCEEDED")
    if context.leverage_adjusted_exposure_pct + add_pct > base.max_leverage_adjusted_exposure_pct:
        warnings.append("LEVERAGE_ADJUSTED_EXPOSURE_LIMIT_EXCEEDED")
    if add_pct > 0 and context.cash_pct - add_pct < base.min_cash_pct:
        warnings.append("MIN_CASH_LIMIT_EXCEEDED")

    if warnings:
        reason_codes.append("PORTFOLIO_POLICY_BLOCK")
    else:
        reason_codes.append("PORTFOLIO_POLICY_PASS")

    passed = not any(
        code.endswith("_EXCEEDED") or code == "MIN_CASH_LIMIT_EXCEEDED"
        for code in warnings
    )
    fit_score = 1.0 if passed else max(0.0, 1.0 - 0.15 * len(set(warnings)))
    return PortfolioGateResult(
        passed=passed,
        portfolio_fit_score=round(fit_score, 4),
        current_weight_pct=context.current_weight_pct,
        max_position_pct=base.max_single_name_weight_pct,
        concentration_warnings=tuple(dict.fromkeys(warnings)),
        reason_codes=tuple(reason_codes),
    )


def trim_or_sell_allowed(policy: AutopmPortfolioPolicy | AutopmPolicy | None) -> bool:
    if policy is None:
        return default_policy().sell_allowed
    if isinstance(policy, AutopmPortfolioPolicy):
        return policy.base_policy.sell_allowed
    return policy.sell_allowed


def _current_weight_pct(snapshot: PortfolioSnapshot, ticker: str) -> float:
    weights = snapshot.base_market_value_weights
    return weights.get(ticker.upper(), 0.0) * 100.0


def _exposure_pct(exposure: dict[str, float], key: str) -> float:
    if not key:
        return 0.0
    return exposure.get(key, 0.0) * 100.0


def _concentration_warnings(
    policy: AutopmPortfolioPolicy,
    current_weight_pct: float,
    theme_pct: float,
    region_pct: float,
    sector_pct: float,
    issuer_pct: float,
    leverage_pct: float,
    cash_pct: float,
) -> tuple[str, ...]:
    base = policy.base_policy
    warnings: list[str] = []
    if current_weight_pct > base.max_single_name_weight_pct:
        warnings.append("CURRENT_SINGLE_NAME_EXCEEDS_POLICY")
    if theme_pct > base.max_theme_weight_pct:
        warnings.append("CURRENT_THEME_EXCEEDS_POLICY")
    if region_pct > base.max_region_weight_pct:
        warnings.append("CURRENT_REGION_EXCEEDS_POLICY")
    if sector_pct > policy.max_sector_weight_pct:
        warnings.append("CURRENT_SECTOR_EXCEEDS_POLICY")
    if issuer_pct > policy.max_issuer_weight_pct:
        warnings.append("CURRENT_ISSUER_EXCEEDS_POLICY")
    if leverage_pct > base.max_leverage_adjusted_exposure_pct:
        warnings.append("CURRENT_LEVERAGE_EXCEEDS_POLICY")
    if cash_pct < base.min_cash_pct:
        warnings.append("CURRENT_CASH_BELOW_POLICY")
    return tuple(warnings)
