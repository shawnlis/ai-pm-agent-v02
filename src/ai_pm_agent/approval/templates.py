"""Static text and field definitions for approval packets."""

from __future__ import annotations


MANIFEST_FIELDS = [
    "approved",
    "rank",
    "ticker",
    "company",
    "market",
    "queue",
    "refresh_score",
    "latest_action",
    "latest_rating",
    "pm_score",
    "chokepoint_score",
    "confidence",
    "latest_run_date",
    "warning_count",
    "evidence_count",
    "fact_count",
    "reason_codes",
    "suggested_manual_command",
    "dossier_path",
    "artifact_path",
    "notes",
]

COMMAND_BUNDLE_HEADER = "DO NOT RUN AUTOMATICALLY. REVIEW AND APPROVE EACH COMMAND FIRST."

APPROVAL_CHECKLIST = [
    "Review urgent_refresh queue.",
    "Remove any irrelevant tickers.",
    "Confirm market suffixes are correct.",
    "Confirm company names are correct.",
    "Confirm whether to run only urgent_refresh or urgent + high_priority.",
    "Confirm whether live LLM/web/yfinance calls are allowed for the next phase.",
    "Confirm whether output should overwrite or create new dated folders.",
    "Confirm no secrets are exposed.",
    "Approve manual rerun batch.",
]

KNOWN_LIMITATIONS = [
    "Offline review packet only.",
    "No live freshness verification is performed.",
    "No rerun execution is performed.",
    "Suggested command syntax is a conservative template and must be checked before use.",
    "The source of truth is SQLite DB data, not parsed Markdown reports.",
    "A human must approve any live research run.",
]

REASON_GROUPS = [
    (
        "stale data",
        {
            "stale_gt_30d",
            "stale_gt_14d",
            "stale_gt_7d",
            "missing_latest_run_date",
        },
    ),
    (
        "high chokepoint score",
        {
            "high_chokepoint_score",
            "high_chokepoint_low_confidence",
            "high_chokepoint_low_evidence",
        },
    ),
    ("high PM score", {"high_pm_score"}),
    ("low confidence", {"low_confidence", "confidence_missing", "high_chokepoint_low_confidence"}),
    ("weak evidence", {"weak_evidence", "no_evidence_items", "high_chokepoint_low_evidence"}),
    ("no facts", {"no_facts"}),
    ("high warnings", {"high_warning_count"}),
    (
        "decision/action/rating changes",
        {"action_changed", "rating_changed", "pm_score_changed", "chokepoint_score_changed"},
    ),
    ("score divergence", {"score_divergence"}),
]


def dossier_path_for_ticker(ticker: str) -> str:
    """Return the conventional dossier path if it exists, otherwise N/A."""
    from pathlib import Path

    safe = ticker.replace("/", "_").replace("\\", "_").replace(":", "_")
    candidates = [
        Path("reports") / "company_dossiers" / f"{safe}.md",
        Path("reports") / "company_dossiers" / f"{safe.replace('.', '_')}.md",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return "N/A"
