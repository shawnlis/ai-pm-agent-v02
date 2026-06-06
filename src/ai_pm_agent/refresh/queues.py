"""Queue names and reason-code explanations for refresh planning."""

from __future__ import annotations


URGENT_REFRESH = "urgent_refresh"
HIGH_PRIORITY = "high_priority"
NORMAL_REFRESH = "normal_refresh"
MONITOR_ONLY = "monitor_only"
NO_REFRESH_NEEDED = "no_refresh_needed"

QUEUE_ORDER = [
    URGENT_REFRESH,
    HIGH_PRIORITY,
    NORMAL_REFRESH,
    MONITOR_ONLY,
    NO_REFRESH_NEEDED,
]

REASON_EXPLANATIONS = {
    "stale_gt_30d": "Latest indexed run is older than 30 days.",
    "stale_gt_14d": "Latest indexed run is older than 14 days.",
    "stale_gt_7d": "Latest indexed run is older than 7 days.",
    "missing_latest_run_date": "No latest run date is indexed.",
    "missing_pm_decision": "Latest run has no parsed PM decision row.",
    "missing_market_snapshot": "Latest run has no parsed market snapshot row.",
    "missing_chokepoint_assessment": "Latest run has no parsed chokepoint assessment row.",
    "no_evidence_items": "Latest run has zero indexed evidence items.",
    "no_facts": "Latest run has zero indexed fact rows.",
    "high_warning_count": "Latest run has a high missing-artifact/import-warning count.",
    "high_chokepoint_score": "Latest run has a high chokepoint score.",
    "high_pm_score": "Latest run has a high PM score.",
    "action_relevant": "Latest action suggests the company remains relevant for monitoring.",
    "low_confidence": "Latest decision confidence is low.",
    "confidence_missing": "Latest decision confidence is missing.",
    "weak_evidence": "Evidence level is missing or weak.",
    "high_chokepoint_low_confidence": "High chokepoint score is paired with low confidence.",
    "high_chokepoint_low_evidence": "High chokepoint score is paired with fewer than five evidence rows.",
    "score_divergence": "PM score and chokepoint score diverge strongly.",
    "action_changed": "Latest action changed from the prior indexed run.",
    "rating_changed": "Latest rating changed from the prior indexed run.",
    "pm_score_changed": "PM score changed by at least 1.0 from the prior indexed run.",
    "chokepoint_score_changed": "Chokepoint score changed by at least 1.0 from the prior indexed run.",
}


def classify_queue(
    score: int,
    reason_codes: list[str],
    has_missing_core: bool,
    has_high_chokepoint_quality_issue: bool,
) -> str:
    if score >= 80 or has_missing_core or has_high_chokepoint_quality_issue:
        return URGENT_REFRESH
    if score >= 60:
        return HIGH_PRIORITY
    if score >= 35:
        return NORMAL_REFRESH
    if score >= 15:
        return MONITOR_ONLY
    return NO_REFRESH_NEEDED
