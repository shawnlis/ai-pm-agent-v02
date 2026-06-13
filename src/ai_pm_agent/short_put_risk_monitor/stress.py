"""Stress scenarios for fixture-only short put risk rows."""

from __future__ import annotations

from ai_pm_agent.short_put_risk_monitor.models import (
    MISSING_UNDERLYING_PRICE,
    NEEDS_REVIEW,
    REVIEW_NEEDS_REVIEW,
    REVIEW_OK,
    ShortPutPosition,
)


def calculate_stress_rows(
    positions: list[ShortPutPosition],
    *,
    position_warning_codes: dict[str, list[str]] | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for position in positions:
        for scenario, stress_price, source in _stress_prices(position):
            rows.append(
                _stress_row(
                    position,
                    scenario=scenario,
                    stress_price=stress_price,
                    source=source,
                    base_warning_codes=(position_warning_codes or {}).get(position.option_id),
                )
            )
    return rows


def _stress_prices(position: ShortPutPosition) -> list[tuple[str, float | None, str]]:
    price = position.current_underlying_price
    return [
        ("underlying -10%", None if price is None else price * 0.90, "current_underlying_price"),
        ("underlying -20%", None if price is None else price * 0.80, "current_underlying_price"),
        ("underlying -30%", None if price is None else price * 0.70, "current_underlying_price"),
        ("underlying to strike", position.strike, "strike"),
        ("underlying to breakeven", position.breakeven_price, "breakeven_price"),
    ]


def _stress_row(
    position: ShortPutPosition,
    *,
    scenario: str,
    stress_price: float | None,
    source: str,
    base_warning_codes: list[str] | None = None,
) -> dict[str, object]:
    warning_codes = list(base_warning_codes if base_warning_codes is not None else position.warning_codes)
    if stress_price is None:
        warning_codes.append(MISSING_UNDERLYING_PRICE)
    warning_codes = _normalized_warning_codes(warning_codes)
    intrinsic_loss = 0.0 if stress_price is None else max(position.strike - stress_price, 0.0) * position.underlying_units
    estimated_pnl = position.premium_collected - intrinsic_loss
    simple_downside = max(intrinsic_loss - position.premium_collected, 0.0)
    return {
        "option_id": position.option_id,
        "underlying_ticker": position.underlying_ticker,
        "scenario": scenario,
        "stress_price": "" if stress_price is None else round(stress_price, 6),
        "stress_price_source": source,
        "gross_notional": round(position.gross_notional, 6),
        "assignment_notional": round(position.assignment_notional, 6),
        "intrinsic_loss_at_stress": round(intrinsic_loss, 6),
        "premium_collected": round(position.premium_collected, 6),
        "max_simple_downside_at_stress": round(simple_downside, 6),
        "estimated_pnl_at_stress": round(estimated_pnl, 6),
        "review_status": REVIEW_NEEDS_REVIEW if warning_codes else REVIEW_OK,
        "warning_codes": ";".join(warning_codes),
    }


def _normalized_warning_codes(codes: list[str]) -> list[str]:
    ordered = list(dict.fromkeys(codes))
    if ordered and NEEDS_REVIEW not in ordered:
        ordered.append(NEEDS_REVIEW)
    return sorted(ordered)
