"""Risk calculations for fixture-only short put rows."""

from __future__ import annotations

from datetime import date

from ai_pm_agent.short_put_risk_monitor.models import (
    BELOW_BREAKEVEN,
    BELOW_STRIKE,
    EXPIRED_OPTION,
    LARGE_ASSIGNMENT_NOTIONAL,
    NEAR_STRIKE,
    NEEDS_REVIEW,
    REVIEW_NEEDS_REVIEW,
    REVIEW_OK,
    ShortPutPosition,
)


NEAR_STRIKE_THRESHOLD_PCT = 0.05
LARGE_ASSIGNMENT_NOTIONAL_THRESHOLD = 100_000.0


def build_position_rows(positions: list[ShortPutPosition], *, as_of_date: date) -> list[dict[str, object]]:
    return [position_as_row(position, as_of_date=as_of_date) for position in positions]


def position_as_row(position: ShortPutPosition, *, as_of_date: date) -> dict[str, object]:
    warning_codes = list(position.warning_codes)
    days_to_expiry = _days_to_expiry(position, as_of_date)

    if days_to_expiry is not None and days_to_expiry < 0:
        warning_codes.append(EXPIRED_OPTION)

    if position.current_underlying_price is not None:
        if position.current_underlying_price < position.breakeven_price:
            warning_codes.append(BELOW_BREAKEVEN)
        if position.current_underlying_price < position.strike:
            warning_codes.append(BELOW_STRIKE)
        elif _distance_to_strike_pct(position) <= NEAR_STRIKE_THRESHOLD_PCT:
            warning_codes.append(NEAR_STRIKE)

    if position.assignment_notional >= LARGE_ASSIGNMENT_NOTIONAL_THRESHOLD:
        warning_codes.append(LARGE_ASSIGNMENT_NOTIONAL)

    warning_codes = _normalized_warning_codes(warning_codes)
    review_status = REVIEW_NEEDS_REVIEW if warning_codes else REVIEW_OK
    return {
        "option_id": position.option_id,
        "underlying_ticker": position.underlying_ticker,
        "expiry_date": position.expiry_date.isoformat() if position.expiry_date else "",
        "days_to_expiry": "" if days_to_expiry is None else days_to_expiry,
        "strike": position.strike,
        "contracts": position.contracts,
        "contract_multiplier": position.contract_multiplier,
        "premium_collected": position.premium_collected,
        "current_underlying_price": "" if position.current_underlying_price is None else position.current_underlying_price,
        "currency": position.currency,
        "underlying_theme": position.underlying_theme,
        "gross_notional": round(position.gross_notional, 6),
        "assignment_notional": round(position.assignment_notional, 6),
        "breakeven_price": round(position.breakeven_price, 6),
        "distance_to_strike_pct": _blank_or_round(_distance_to_strike_pct(position)),
        "distance_to_breakeven_pct": _blank_or_round(_distance_to_breakeven_pct(position)),
        "review_status": review_status,
        "warning_codes": ";".join(warning_codes),
        "notes": position.notes or "",
    }


def collect_warning_codes(rows: list[dict[str, object]]) -> list[str]:
    codes: set[str] = set()
    for row in rows:
        text = str(row.get("warning_codes", ""))
        for code in text.split(";"):
            if code:
                codes.add(code)
    return sorted(codes)


def calculate_totals(rows: list[dict[str, object]]) -> dict[str, float]:
    return {
        "gross_notional": sum(float(row["gross_notional"]) for row in rows),
        "assignment_notional": sum(float(row["assignment_notional"]) for row in rows),
        "premium_collected": sum(float(row["premium_collected"]) for row in rows),
    }


def _days_to_expiry(position: ShortPutPosition, as_of_date: date) -> int | None:
    if position.expiry_date is None:
        return None
    return (position.expiry_date - as_of_date).days


def _distance_to_strike_pct(position: ShortPutPosition) -> float | None:
    if position.current_underlying_price is None:
        return None
    return (position.current_underlying_price - position.strike) / position.strike


def _distance_to_breakeven_pct(position: ShortPutPosition) -> float | None:
    if position.current_underlying_price is None or position.breakeven_price == 0:
        return None
    return (position.current_underlying_price - position.breakeven_price) / position.breakeven_price


def _blank_or_round(value: float | None) -> str | float:
    if value is None:
        return ""
    return round(value, 10)


def _normalized_warning_codes(codes: list[str]) -> list[str]:
    ordered = list(dict.fromkeys(codes))
    if ordered and NEEDS_REVIEW not in ordered:
        ordered.append(NEEDS_REVIEW)
    return sorted(ordered)
