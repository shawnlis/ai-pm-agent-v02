"""Input and output contracts for Risk Cockpit Pipeline v0.5.2."""

from __future__ import annotations


MARKET_DATA_FIXTURE_FIELDS = [
    "ticker",
    "price",
    "currency",
    "as_of_date",
    "source",
    "source_confidence",
    "fixture_only",
    "notes",
]

ARTIFACT_SUMMARY_FIELDS = [
    "artifact_type",
    "path",
    "exists",
    "status",
    "row_count",
    "warning_count",
    "review_required",
    "notes",
]

WARNING_SUMMARY_FIELDS = [
    "source",
    "warning_code",
    "count",
    "review_required",
    "notes",
]

MARKET_DATA_SNAPSHOT_FIELDS = [
    "ticker",
    "price",
    "currency",
    "as_of_date",
    "source",
    "source_confidence",
    "fixture_only",
    "status",
    "warning_codes",
    "notes",
]

ENRICHMENT_SUMMARY_FIELDS = [
    "ticker",
    "source_context",
    "market_data_available",
    "market_price",
    "market_data_as_of_date",
    "market_data_currency",
    "stale_market_data",
    "warning_codes",
    "review_required",
    "notes",
]

REPORT_FILENAME = "RISK_COCKPIT_PIPELINE_V052.md"
INDEX_FILENAME = "risk_cockpit_pipeline_index.json"
ARTIFACT_SUMMARY_FILENAME = "risk_artifact_summary.csv"
WARNING_SUMMARY_FILENAME = "risk_warning_summary.csv"
MARKET_DATA_SNAPSHOT_FILENAME = "market_data_snapshot.csv"
ENRICHMENT_SUMMARY_FILENAME = "risk_enrichment_summary.csv"
WARNINGS_FILENAME = "risk_cockpit_pipeline_warnings.md"
