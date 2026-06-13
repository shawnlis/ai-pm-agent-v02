"""Deterministic thesis-gap classification rules."""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Iterable

from .evidence_reader import manifest_sources, manifest_warning_codes
from .models import (
    GAP_STATUSES,
    THEMES,
    EvidenceBundle,
    MonitorResult,
    SourceCoverage,
    ThemeDefinition,
    ThesisGap,
    stable_gap_id,
)


NO_MATCHING_EVIDENCE = "NO_MATCHING_EVIDENCE"
MISSING_COMPANY_EVIDENCE = "MISSING_COMPANY_EVIDENCE"
MISSING_SOURCE_DATE = "MISSING_SOURCE_DATE"
STALE_EVIDENCE = "STALE_EVIDENCE"
AMBIGUOUS_EVIDENCE = "AMBIGUOUS_EVIDENCE"
WEAK_EVIDENCE_ONLY = "WEAK_EVIDENCE_ONLY"
ROI_RISK = "ROI_RISK"
RISK_EVIDENCE_PRESENT = "RISK_EVIDENCE_PRESENT"

STRONG_CLOSE_TERMS = (
    "material revenue",
    "recognized revenue",
    "revenue contribution",
    "contracted revenue",
    "remaining performance obligation",
    "volume production with revenue",
    "commercial shipment",
    "customer commitment",
)

PARTIAL_CLOSE_TERMS = (
    "sample",
    "qualification",
    "qualified",
    "pilot",
    "design win",
    "ramp",
    "production",
    "shipment",
    "capacity expansion",
    "supply agreement",
    "backlog",
)

AMBIGUOUS_TERMS = (
    "may",
    "could",
    "expects",
    "expected",
    "plans",
    "intends",
    "target",
    "potential",
    "evaluating",
    "early",
)


def evaluate_gaps(
    bundle: EvidenceBundle,
    *,
    companies: Iterable[str],
    as_of_date: date | None = None,
    stale_days: int = 548,
) -> MonitorResult:
    as_of = as_of_date or date.today()
    tickers = [ticker.strip().upper() for ticker in companies if ticker.strip()]
    ledger_by_ticker = _group_by_ticker(bundle.ledger_rows)
    metrics_by_ticker = _group_by_ticker(bundle.metric_rows)
    manifest_codes = manifest_warning_codes(bundle.manifest)

    gaps: list[ThesisGap] = []
    coverage: list[SourceCoverage] = []
    for ticker in tickers:
        ticker_ledger = ledger_by_ticker.get(ticker, [])
        ticker_metrics = metrics_by_ticker.get(ticker, [])
        company_name = _company_name(ticker, ticker_ledger, ticker_metrics, bundle)
        coverage.append(
            _source_coverage(
                ticker=ticker,
                company_name=company_name,
                ledger_rows=ticker_ledger,
                metric_rows=ticker_metrics,
                manifest=bundle.manifest,
                manifest_warning_codes=manifest_codes,
                as_of_date=as_of,
                stale_days=stale_days,
            )
        )
        for theme in THEMES:
            gaps.append(
                _evaluate_company_theme(
                    ticker=ticker,
                    theme=theme,
                    ledger_rows=ticker_ledger,
                    metric_rows=ticker_metrics,
                    manifest_warning_codes=manifest_codes,
                    as_of_date=as_of,
                    stale_days=stale_days,
                )
            )

    status_counts = {status: 0 for status in GAP_STATUSES}
    status_counts.update(Counter(gap.current_status for gap in gaps))
    warnings = tuple(
        sorted(
            {code for gap in gaps for code in gap.warning_codes}
            | {code for source in coverage for code in source.warning_codes}
        )
    )
    return MonitorResult(
        gaps=gaps,
        coverage=coverage,
        status_counts=status_counts,
        warning_codes=warnings,
        manifest_summary={
            "api_level": bundle.manifest.get("api_level", "UNKNOWN"),
            "fixture_only": bundle.manifest.get("fixture_only", "UNKNOWN"),
            "network_access": bundle.manifest.get("network_access", "UNKNOWN"),
            "live_sec_api": bundle.manifest.get("live_sec_api", "UNKNOWN"),
            "source_count": len(manifest_sources(bundle.manifest)),
            "input_ledger": str(bundle.input_paths.ledger_csv),
            "input_metric_history": str(bundle.input_paths.metric_history_csv),
            "input_source_manifest": str(bundle.input_paths.source_manifest_json),
            "input_evidence_db": str(bundle.input_paths.evidence_db_sqlite or ""),
        },
    )


def _evaluate_company_theme(
    *,
    ticker: str,
    theme: ThemeDefinition,
    ledger_rows: list[dict[str, str]],
    metric_rows: list[dict[str, str]],
    manifest_warning_codes: tuple[str, ...],
    as_of_date: date,
    stale_days: int,
) -> ThesisGap:
    matching_ledger = [row for row in ledger_rows if _row_matches_theme(row, theme)]
    matching_metrics = [row for row in metric_rows if _row_matches_theme(row, theme)]
    matched_rows = matching_ledger + matching_metrics
    source_count = len({_source_key(row) for row in matched_rows if _source_key(row)})
    newest_source_date = _newest_date(matched_rows)
    missing_source_date = bool(matched_rows) and not newest_source_date
    stale = _is_stale(newest_source_date, as_of_date=as_of_date, stale_days=stale_days)
    warning_codes = set(manifest_warning_codes)

    if not ledger_rows and not metric_rows:
        warning_codes.add(MISSING_COMPANY_EVIDENCE)
        return _gap(
            ticker=ticker,
            theme=theme,
            status="UNKNOWN",
            summary="No source-backed evidence rows were found for this company.",
            source_count=0,
            newest_source_date="",
            confidence="low",
            warning_codes=warning_codes,
            human_review_required=True,
        )

    if not matched_rows:
        warning_codes.add(NO_MATCHING_EVIDENCE)
        return _gap(
            ticker=ticker,
            theme=theme,
            status="UNKNOWN",
            summary="No source-backed evidence matched this theme.",
            source_count=0,
            newest_source_date="",
            confidence="low",
            warning_codes=warning_codes,
            human_review_required=True,
        )

    text_blob = " ".join(_row_text(row) for row in matched_rows).lower()
    risk_present = any(term in text_blob for term in theme.risk_keywords) or _contains_any(text_blob, _global_risk_terms())
    strong_present = _contains_any(text_blob, STRONG_CLOSE_TERMS)
    partial_present = _contains_any(text_blob, PARTIAL_CLOSE_TERMS)
    ambiguous_present = _contains_any(text_blob, AMBIGUOUS_TERMS)
    capex_without_monetization = (
        theme.theme_id in {"ai_capex", "data_center_margin_capex_burden", "cloud_infrastructure"}
        and ("capex" in text_blob or "capital expenditure" in text_blob)
        and not strong_present
    )

    status = "UNCHANGED"
    confidence = "medium"
    human_review_required = False
    if risk_present:
        status = "WORSENED"
        warning_codes.add(RISK_EVIDENCE_PRESENT)
        human_review_required = True
    elif capex_without_monetization:
        status = "NEEDS_REVIEW"
        warning_codes.add(ROI_RISK)
        human_review_required = True
    elif strong_present:
        status = "CLOSED"
        confidence = "high" if source_count >= 2 else "medium"
    elif partial_present:
        status = "PARTIALLY_CLOSED"
        warning_codes.add(WEAK_EVIDENCE_ONLY)
        human_review_required = True
    elif ambiguous_present:
        status = "NEEDS_REVIEW"
        warning_codes.add(AMBIGUOUS_EVIDENCE)
        human_review_required = True

    if missing_source_date:
        warning_codes.add(MISSING_SOURCE_DATE)
        confidence = "low"
        human_review_required = True
        if status == "CLOSED":
            status = "PARTIALLY_CLOSED"
        elif status == "UNCHANGED":
            status = "NEEDS_REVIEW"

    if stale:
        warning_codes.add(STALE_EVIDENCE)
        confidence = "low"
        human_review_required = True
        if status == "CLOSED":
            status = "PARTIALLY_CLOSED"
        elif status == "UNCHANGED":
            status = "NEEDS_REVIEW"

    return _gap(
        ticker=ticker,
        theme=theme,
        status=status,
        summary=_evidence_summary(matched_rows),
        source_count=source_count,
        newest_source_date=newest_source_date,
        confidence=confidence,
        warning_codes=warning_codes,
        human_review_required=human_review_required,
    )


def _source_coverage(
    *,
    ticker: str,
    company_name: str,
    ledger_rows: list[dict[str, str]],
    metric_rows: list[dict[str, str]],
    manifest: dict[str, object],
    manifest_warning_codes: tuple[str, ...],
    as_of_date: date,
    stale_days: int,
) -> SourceCoverage:
    all_rows = ledger_rows + metric_rows
    source_count = len({_source_key(row) for row in all_rows if _source_key(row)})
    newest = _newest_date(all_rows)
    stale = _is_stale(newest, as_of_date=as_of_date, stale_days=stale_days)
    warning_codes = set(manifest_warning_codes)
    if not all_rows:
        warning_codes.add(MISSING_COMPANY_EVIDENCE)
        status = "NO_COMPANY_EVIDENCE"
    elif not newest:
        warning_codes.add(MISSING_SOURCE_DATE)
        status = "NEEDS_REVIEW"
    elif stale:
        warning_codes.add(STALE_EVIDENCE)
        status = "STALE"
    else:
        status = "COVERED"
    return SourceCoverage(
        company=ticker,
        company_name=company_name,
        evidence_rows=len(ledger_rows),
        metric_rows=len(metric_rows),
        source_count=source_count or _manifest_source_count(ticker, manifest),
        newest_source_date=newest,
        warning_codes=tuple(sorted(warning_codes)),
        coverage_status=status,
    )


def _gap(
    *,
    ticker: str,
    theme: ThemeDefinition,
    status: str,
    summary: str,
    source_count: int,
    newest_source_date: str,
    confidence: str,
    warning_codes: set[str],
    human_review_required: bool,
) -> ThesisGap:
    return ThesisGap(
        company=ticker,
        theme=theme.theme,
        gap_id=stable_gap_id(ticker, theme.theme_id),
        gap_question=theme.gap_question,
        current_status=status,
        evidence_summary=summary,
        source_count=source_count,
        newest_source_date=newest_source_date,
        confidence=confidence,
        warning_codes=tuple(sorted(warning_codes)),
        human_review_required=human_review_required,
        why_it_matters=theme.why_it_matters,
        what_would_close_the_gap=theme.what_would_close_the_gap,
    )


def _row_matches_theme(row: dict[str, str], theme: ThemeDefinition) -> bool:
    text = _row_text(row).lower()
    return any(keyword in text for keyword in theme.keywords)


def _row_text(row: dict[str, str]) -> str:
    fields = [
        "company_name",
        "source_type",
        "source_name",
        "evidence_type",
        "metric_or_form",
        "taxonomy",
        "concept",
        "label",
        "unit",
        "review_status",
        "confidence",
    ]
    return " ".join(str(row.get(field, "")) for field in fields)


def _evidence_summary(rows: list[dict[str, str]]) -> str:
    snippets: list[str] = []
    for row in rows[:3]:
        label = row.get("metric_or_form") or row.get("concept") or row.get("source_name") or "evidence"
        source_date = row.get("source_date") or row.get("filed_date") or row.get("end_date") or "UNKNOWN_DATE"
        snippets.append(f"{label} ({source_date})")
    extra_count = max(0, len(rows) - len(snippets))
    summary = "; ".join(snippets)
    if extra_count:
        summary += f"; plus {extra_count} additional source-backed rows"
    return summary or "No source-backed evidence matched this theme."


def _group_by_ticker(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        ticker = str(row.get("ticker", "")).strip().upper()
        if not ticker:
            continue
        grouped.setdefault(ticker, []).append(row)
    return grouped


def _company_name(
    ticker: str,
    ledger_rows: list[dict[str, str]],
    metric_rows: list[dict[str, str]],
    bundle: EvidenceBundle,
) -> str:
    for row in ledger_rows + metric_rows:
        name = row.get("company_name", "").strip()
        if name:
            return name
    for source in manifest_sources(bundle.manifest):
        if str(source.get("ticker", "")).strip().upper() == ticker:
            return str(source.get("company_name", "")).strip()
    return ""


def _source_key(row: dict[str, str]) -> str:
    return row.get("source_hash") or row.get("source_path") or row.get("accession_number") or ""


def _newest_date(rows: list[dict[str, str]]) -> str:
    parsed_dates = []
    for row in rows:
        for field in ("source_date", "filing_date", "filed_date", "end_date"):
            parsed = _parse_date(row.get(field, ""))
            if parsed is not None:
                parsed_dates.append(parsed)
                break
    return max(parsed_dates).isoformat() if parsed_dates else ""


def _is_stale(newest_source_date: str, *, as_of_date: date, stale_days: int) -> bool:
    parsed = _parse_date(newest_source_date)
    if parsed is None:
        return False
    return parsed < as_of_date - timedelta(days=stale_days)


def _parse_date(raw: str) -> date | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _global_risk_terms() -> tuple[str, ...]:
    return (
        "margin pressure",
        "capex burden",
        "roi risk",
        "slowdown",
        "inventory correction",
        "oversupply",
        "delay",
        "cancellation",
        "customer concentration",
        "without revenue",
    )


def _manifest_source_count(ticker: str, manifest: dict[str, object]) -> int:
    return len(
        [
            source
            for source in manifest_sources(manifest)
            if str(source.get("ticker", "")).strip().upper() == ticker
        ]
    )
