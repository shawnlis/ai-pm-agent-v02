"""Deterministic refresh scoring rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .queues import classify_queue


@dataclass(frozen=True)
class ScoreSignal:
    code: str
    points: int


@dataclass(frozen=True)
class ScoreResult:
    score: int
    queue: str
    signals: tuple[ScoreSignal, ...]

    @property
    def reason_codes(self) -> list[str]:
        return [signal.code for signal in self.signals]


def score_refresh_candidate(
    row: dict[str, Any],
    previous: dict[str, Any] | None = None,
    as_of: datetime | None = None,
) -> ScoreResult:
    as_of = as_of or datetime.now(timezone.utc)
    signals: list[ScoreSignal] = []

    _score_staleness(row, as_of, signals)
    _score_completeness(row, signals)
    _score_investment_relevance(row, signals)
    _score_quality(row, signals)
    _score_change_detection(row, previous, signals)

    total = min(100, sum(signal.points for signal in signals))
    reason_codes = [signal.code for signal in signals]
    has_missing_core = any(
        code in reason_codes
        for code in ("missing_pm_decision", "missing_market_snapshot", "missing_chokepoint_assessment")
    )
    has_high_chokepoint_quality_issue = any(
        code in reason_codes
        for code in ("high_chokepoint_low_confidence", "high_chokepoint_low_evidence")
    )
    queue = classify_queue(total, reason_codes, has_missing_core, has_high_chokepoint_quality_issue)
    return ScoreResult(score=total, queue=queue, signals=tuple(signals))


def _score_staleness(row: dict[str, Any], as_of: datetime, signals: list[ScoreSignal]) -> None:
    latest_run_date = _parse_datetime(row.get("latest_run_date"))
    if latest_run_date is None:
        signals.append(ScoreSignal("missing_latest_run_date", 25))
        return
    if latest_run_date.tzinfo is None:
        latest_run_date = latest_run_date.replace(tzinfo=timezone.utc)
    age_days = (as_of - latest_run_date).days
    if age_days > 30:
        signals.append(ScoreSignal("stale_gt_30d", 30))
    elif age_days > 14:
        signals.append(ScoreSignal("stale_gt_14d", 20))
    elif age_days > 7:
        signals.append(ScoreSignal("stale_gt_7d", 10))


def _score_completeness(row: dict[str, Any], signals: list[ScoreSignal]) -> None:
    if _int(row.get("has_pm_decision")) == 0:
        signals.append(ScoreSignal("missing_pm_decision", 40))
    if _int(row.get("has_market_snapshot")) == 0:
        signals.append(ScoreSignal("missing_market_snapshot", 20))
    if _int(row.get("has_chokepoint_assessment")) == 0:
        signals.append(ScoreSignal("missing_chokepoint_assessment", 25))
    evidence_count = _int(row.get("evidence_count"))
    facts_count = _int(row.get("facts_count"))
    if evidence_count == 0:
        signals.append(ScoreSignal("no_evidence_items", 20))
    if facts_count == 0:
        signals.append(ScoreSignal("no_facts", 15))
    warning_count = _int(row.get("warning_count"))
    if warning_count >= 6:
        signals.append(ScoreSignal("high_warning_count", 15))
    elif warning_count >= 3:
        signals.append(ScoreSignal("high_warning_count", 10))
    elif warning_count >= 1:
        signals.append(ScoreSignal("high_warning_count", 5))


def _score_investment_relevance(row: dict[str, Any], signals: list[ScoreSignal]) -> None:
    chokepoint_score = _num(row.get("chokepoint_score"))
    pm_score = _num(row.get("pm_score"))
    if chokepoint_score is not None:
        if chokepoint_score >= 9:
            signals.append(ScoreSignal("high_chokepoint_score", 20))
        elif chokepoint_score >= 8:
            signals.append(ScoreSignal("high_chokepoint_score", 15))
    if pm_score is not None and pm_score >= 7:
        signals.append(ScoreSignal("high_pm_score", 15))

    action = _text(row.get("action")).lower()
    if action in {"buy", "add", "accumulate", "starter_position", "tracking_position"}:
        signals.append(ScoreSignal("action_relevant", 15))
    elif action in {"monitor", "watchlist", "watch"}:
        signals.append(ScoreSignal("action_relevant", 8))
    elif action:
        signals.append(ScoreSignal("action_relevant", 5))


def _score_quality(row: dict[str, Any], signals: list[ScoreSignal]) -> None:
    confidence = _num(row.get("confidence"))
    if confidence is None:
        signals.append(ScoreSignal("confidence_missing", 5))
    elif confidence <= 1:
        signals.append(ScoreSignal("low_confidence", 15))
    elif confidence <= 2:
        signals.append(ScoreSignal("low_confidence", 10))

    evidence_level = _text(row.get("evidence_level")).lower()
    if evidence_level in {"", "n/a", "none", "missing", "weak", "low"}:
        signals.append(ScoreSignal("weak_evidence", 10))

    chokepoint_score = _num(row.get("chokepoint_score"))
    evidence_count = _int(row.get("evidence_count"))
    if chokepoint_score is not None and chokepoint_score >= 8:
        if confidence is not None and confidence <= 2:
            signals.append(ScoreSignal("high_chokepoint_low_confidence", 15))
        if evidence_count < 5:
            signals.append(ScoreSignal("high_chokepoint_low_evidence", 15))

    pm_score = _num(row.get("pm_score"))
    if pm_score is not None and chokepoint_score is not None and abs(pm_score - chokepoint_score) >= 3:
        signals.append(ScoreSignal("score_divergence", 10))


def _score_change_detection(
    row: dict[str, Any],
    previous: dict[str, Any] | None,
    signals: list[ScoreSignal],
) -> None:
    if not previous:
        return
    if _text(previous.get("action")).lower() != _text(row.get("action")).lower():
        signals.append(ScoreSignal("action_changed", 15))
    if _text(previous.get("rating")).lower() != _text(row.get("rating")).lower():
        signals.append(ScoreSignal("rating_changed", 15))

    pm_score = _num(row.get("pm_score"))
    previous_pm_score = _num(previous.get("pm_score"))
    if pm_score is not None and previous_pm_score is not None and abs(pm_score - previous_pm_score) >= 1.0:
        signals.append(ScoreSignal("pm_score_changed", 10))

    chokepoint_score = _num(row.get("chokepoint_score"))
    previous_chokepoint_score = _num(previous.get("chokepoint_score"))
    if (
        chokepoint_score is not None
        and previous_chokepoint_score is not None
        and abs(chokepoint_score - previous_chokepoint_score) >= 1.0
    ):
        signals.append(ScoreSignal("chokepoint_score_changed", 10))


def _parse_datetime(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
