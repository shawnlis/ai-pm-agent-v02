"""Approval manifest CSV helpers."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

from ai_pm_agent.approval.templates import MANIFEST_FIELDS, dossier_path_for_ticker
from ai_pm_agent.refresh.planner import RefreshCandidate
from ai_pm_agent.reports.markdown import write_csv


def manifest_row(candidate: RefreshCandidate) -> dict[str, Any]:
    return {
        "approved": "",
        "rank": candidate.priority_rank,
        "ticker": candidate.ticker,
        "company": candidate.company,
        "market": candidate.market,
        "queue": candidate.queue,
        "refresh_score": candidate.refresh_score,
        "latest_action": candidate.latest_action,
        "latest_rating": candidate.latest_rating,
        "pm_score": candidate.pm_score,
        "chokepoint_score": candidate.chokepoint_score,
        "confidence": candidate.confidence,
        "latest_run_date": candidate.latest_run_date,
        "warning_count": candidate.warning_count,
        "evidence_count": candidate.evidence_count,
        "fact_count": candidate.fact_count,
        "reason_codes": ",".join(candidate.reason_codes),
        "suggested_manual_command": candidate.suggested_manual_command,
        "dossier_path": dossier_path_for_ticker(candidate.ticker),
        "artifact_path": candidate.artifact_path,
        "notes": "",
    }


def manifest_rows(candidates: list[RefreshCandidate] | tuple[RefreshCandidate, ...]) -> list[dict[str, Any]]:
    return [manifest_row(candidate) for candidate in candidates]


def write_manifest(path: Path | str, rows: list[dict[str, Any]]) -> Path:
    return write_csv(path, rows, MANIFEST_FIELDS)


def summarize_manifest(path: Path | str) -> dict[str, Any]:
    target = Path(path)
    rows: list[dict[str, str]] = []
    if target.exists():
        with target.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
    queue_counts = Counter(row.get("queue") or "N/A" for row in rows)
    approved_count = sum(
        1
        for row in rows
        if (row.get("approved") or "").strip().lower() in {"1", "true", "yes", "y", "approved"}
    )
    top_tickers = [row.get("ticker", "") for row in rows[:10] if row.get("ticker")]
    return {
        "path": str(target),
        "exists": target.exists(),
        "row_count": len(rows),
        "approved_count": approved_count,
        "queue_counts": dict(queue_counts),
        "top_tickers": top_tickers,
        "fields": list(rows[0].keys()) if rows else [],
    }
