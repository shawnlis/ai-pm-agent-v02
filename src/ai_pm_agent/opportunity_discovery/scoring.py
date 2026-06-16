"""Deterministic scoring for AI infrastructure opportunity discovery."""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Iterable

from .models import DiscoveryInputBundle, DiscoveryResult, OpportunityCandidate, STATUSES
from .warnings import (
    HIGH_RISK_BLOCKER_PRESENT,
    MISSING_SOURCE_DATE,
    MISSING_THESIS_GAP_DATA,
    MISSING_VALUATION_DATA,
    NO_IMPROVING_GAPS,
    RISK_WARNING_PRESENT,
    STALE_EVIDENCE,
    WEAK_SOURCE_COVERAGE,
    unique_codes,
)


IMPROVING_STATUSES = {"CLOSED", "PARTIALLY_CLOSED"}
WEAK_COVERAGE_STATUSES = {"NO_COMPANY_EVIDENCE", "NEEDS_REVIEW", "STALE", ""}
RISK_CODES = {"RISK_EVIDENCE_PRESENT", "ROI_RISK", "PIPELINE_REVIEW_REQUIRED", "RISK_ARTIFACT_NEEDS_REVIEW"}
HIGH_RISK_SEVERITIES = {"high", "critical", "blocker", "severe"}
CATALYST_TERMS = (
    "commercial shipment",
    "material revenue",
    "revenue contribution",
    "volume production",
    "customer commitment",
    "backlog",
    "remaining performance obligation",
    "hbm",
    "accelerator",
)
VALUATION_TERMS = (
    "valuation",
    "market capitalization",
    "market cap",
    "enterprise value",
    "ev/ebitda",
    "ev/sales",
    "p/e",
    "pe ratio",
    "price earnings",
    "free cash flow yield",
    "fcf yield",
    "multiple",
)


def score_bundle(bundle: DiscoveryInputBundle, *, as_of_date: date | None = None) -> DiscoveryResult:
    del as_of_date
    companies = _companies(bundle)
    gap_rows_by_company = _group_by_company(bundle.thesis_gap_rows)
    coverage_by_company = {
        _ticker(row): row for row in bundle.source_coverage_rows if _ticker(row)
    }
    evidence_rows_by_company = _group_by_company(bundle.ledger_rows + bundle.metric_rows)
    prior_by_company = {
        _ticker(row): row for row in bundle.prior_candidate_rows if _ticker(row)
    }
    high_risk_by_company = _high_risk_companies(bundle.risk_summary_rows, bundle.risk_summary_text)

    candidates = [
        _score_company(
            company=company,
            gap_rows=gap_rows_by_company.get(company, []),
            coverage_row=coverage_by_company.get(company, {}),
            evidence_rows=evidence_rows_by_company.get(company, []),
            prior_row=prior_by_company.get(company, {}),
            high_risk_blocker=company in high_risk_by_company,
        )
        for company in companies
    ]
    candidates.sort(key=lambda candidate: (-candidate.total_score, candidate.status, candidate.company))

    status_counts = {status: 0 for status in STATUSES}
    status_counts.update(Counter(candidate.status for candidate in candidates))
    warning_codes = unique_codes([code for candidate in candidates for code in candidate.warning_codes])
    return DiscoveryResult(
        candidates=candidates,
        status_counts=status_counts,
        warning_codes=warning_codes,
        input_paths=bundle.paths,
    )


def _score_company(
    *,
    company: str,
    gap_rows: list[dict[str, str]],
    coverage_row: dict[str, str],
    evidence_rows: list[dict[str, str]],
    prior_row: dict[str, str],
    high_risk_blocker: bool,
) -> OpportunityCandidate:
    closed = sum(1 for row in gap_rows if row.get("current_status") == "CLOSED")
    partial = sum(1 for row in gap_rows if row.get("current_status") == "PARTIALLY_CLOSED")
    improving = closed + partial
    coverage_source_count = _int_value(coverage_row.get("source_count"))
    gap_source_count = max((_int_value(row.get("source_count")) for row in gap_rows), default=0)
    source_count = coverage_source_count or gap_source_count
    coverage_status = coverage_row.get("coverage_status", "")
    newest_source_date = coverage_row.get("newest_source_date", "")
    warning_codes = set(_warning_codes_from_rows(gap_rows + ([coverage_row] if coverage_row else [])))

    if not gap_rows:
        warning_codes.add(MISSING_THESIS_GAP_DATA)
    if coverage_status in WEAK_COVERAGE_STATUSES or source_count < 1:
        warning_codes.add(WEAK_SOURCE_COVERAGE)
    if not newest_source_date:
        warning_codes.add(MISSING_SOURCE_DATE)
    if coverage_status == "STALE":
        warning_codes.add(STALE_EVIDENCE)
    if warning_codes & RISK_CODES:
        warning_codes.add(RISK_WARNING_PRESENT)
    if high_risk_blocker:
        warning_codes.update({RISK_WARNING_PRESENT, HIGH_RISK_BLOCKER_PRESENT})

    valuation_available = _has_valuation_data(evidence_rows)
    if not valuation_available:
        warning_codes.add(MISSING_VALUATION_DATA)

    catalyst_score = _catalyst_score(gap_rows, evidence_rows)
    evidence_strength = min(30, closed * 14 + partial * 8 + min(source_count, 4) * 2)
    gap_closure = min(25, closed * 12 + partial * 7)
    source_freshness = 15 if coverage_status == "COVERED" and newest_source_date else 0
    valuation_score = 15 if valuation_available else 0
    risk_penalty = 35 if HIGH_RISK_BLOCKER_PRESENT in warning_codes else 25 if RISK_WARNING_PRESENT in warning_codes else 0
    missing_penalty = 0
    if WEAK_SOURCE_COVERAGE in warning_codes:
        missing_penalty += 20
    if MISSING_SOURCE_DATE in warning_codes or STALE_EVIDENCE in warning_codes:
        missing_penalty += 15
    if not gap_rows:
        missing_penalty += 25
    if improving == 0:
        missing_penalty += 10
        warning_codes.add(NO_IMPROVING_GAPS)

    total = max(
        0,
        evidence_strength
        + gap_closure
        + source_freshness
        + catalyst_score
        + valuation_score
        - risk_penalty
        - missing_penalty,
    )
    status = _status(
        improving=improving,
        total=total,
        coverage_status=coverage_status,
        valuation_available=valuation_available,
        catalyst_score=catalyst_score,
        warning_codes=warning_codes,
        positive_evidence_present=improving > 0 and (closed > 0 or partial > 0),
    )
    transition = _transition(prior_row, status, total)
    unresolved_blockers = _unresolved_blockers(
        warning_codes=warning_codes,
        valuation_available=valuation_available,
        coverage_status=coverage_status,
        risk_penalty=risk_penalty,
    )
    return OpportunityCandidate(
        company=company,
        company_name=_company_name(company, coverage_row, evidence_rows),
        status=status,
        total_score=total,
        evidence_strength_score=evidence_strength,
        gap_closure_score=gap_closure,
        source_freshness_score=source_freshness,
        catalyst_signal_score=catalyst_score,
        valuation_data_availability_score=valuation_score,
        risk_blocker_penalty=risk_penalty,
        missing_data_penalty=missing_penalty,
        improving_gap_count=improving,
        closed_gap_count=closed,
        partially_closed_gap_count=partial,
        source_count=source_count,
        newest_source_date=newest_source_date,
        valuation_data_available=valuation_available,
        source_coverage_status=coverage_status or "UNKNOWN",
        prior_status=transition["prior_status"],
        current_status=status,
        status_change=transition["status_change"],
        score_delta=transition["score_delta"],
        newly_promoted=transition["newly_promoted"],
        newly_downgraded=transition["newly_downgraded"],
        unchanged=transition["unchanged"],
        why_this_status=_why_this_status(
            status=status,
            improving=improving,
            valuation_available=valuation_available,
            coverage_status=coverage_status,
            risk_penalty=risk_penalty,
            warning_codes=warning_codes,
        ),
        what_would_upgrade=_what_would_upgrade(status, unresolved_blockers),
        what_would_downgrade=_what_would_downgrade(status),
        unresolved_blockers=unresolved_blockers,
        required_next_evidence=_required_next_evidence(status, unresolved_blockers),
        not_investment_advice=True,
        warning_codes=unique_codes(warning_codes),
        review_note=_review_note(status),
    )


def _status(
    *,
    improving: int,
    total: int,
    coverage_status: str,
    valuation_available: bool,
    catalyst_score: int,
    warning_codes: set[str],
    positive_evidence_present: bool,
) -> str:
    weak_or_stale = WEAK_SOURCE_COVERAGE in warning_codes or MISSING_SOURCE_DATE in warning_codes or STALE_EVIDENCE in warning_codes
    if RISK_WARNING_PRESENT in warning_codes:
        return "RISK_BLOCKED"
    if weak_or_stale and improving == 0:
        return "EVIDENCE_BLOCKED"
    if weak_or_stale:
        return "WATCHLIST_ONLY"
    if improving == 0:
        return "WATCHLIST_ONLY"
    if not valuation_available and improving >= 2:
        return "THESIS_IMPROVING"
    if not valuation_available:
        return "VALUATION_BLOCKED"
    if coverage_status == "COVERED" and total >= 70 and positive_evidence_present:
        return "OPPORTUNITY_REVIEW"
    if catalyst_score > 0:
        return "CATALYST_MONITOR"
    return "THESIS_IMPROVING"


def _companies(bundle: DiscoveryInputBundle) -> list[str]:
    companies = {_ticker(row) for row in bundle.source_coverage_rows + bundle.thesis_gap_rows + bundle.ledger_rows + bundle.metric_rows}
    return sorted(company for company in companies if company)


def _group_by_company(rows: Iterable[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        ticker = _ticker(row)
        if ticker:
            grouped.setdefault(ticker, []).append(row)
    return grouped


def _ticker(row: dict[str, str]) -> str:
    return str(row.get("company") or row.get("ticker") or "").strip().upper()


def _warning_codes_from_rows(rows: list[dict[str, str]]) -> list[str]:
    codes: list[str] = []
    for row in rows:
        raw = str(row.get("warning_codes", ""))
        codes.extend(code.strip() for code in raw.replace(",", ";").split(";") if code.strip())
    return codes


def _high_risk_companies(rows: list[dict[str, str]], text: str) -> set[str]:
    tickers: set[str] = set()
    for row in rows:
        ticker = _ticker(row)
        row_text = _row_text(row).lower()
        severity = str(row.get("severity") or row.get("risk_severity") or row.get("level") or "").strip().lower()
        code = str(row.get("warning_code") or row.get("code") or row.get("warning_codes") or "").upper()
        high = severity in HIGH_RISK_SEVERITIES or "HIGH" in code or "BLOCKER" in code
        if ticker and high:
            tickers.add(ticker)
        if ticker and "high" in row_text and "risk" in row_text:
            tickers.add(ticker)
    for line in text.splitlines():
        lowered = line.lower()
        if "high" not in lowered and "blocker" not in lowered:
            continue
        for token in line.replace("|", " ").replace(",", " ").split():
            cleaned = "".join(ch for ch in token if ch.isalnum()).upper()
            if 1 < len(cleaned) <= 5:
                tickers.add(cleaned)
    return tickers


def _has_valuation_data(rows: list[dict[str, str]]) -> bool:
    return any(any(term in _row_text(row).lower() for term in VALUATION_TERMS) for row in rows)


def _catalyst_score(gap_rows: list[dict[str, str]], evidence_rows: list[dict[str, str]]) -> int:
    text = " ".join(_row_text(row) for row in gap_rows + evidence_rows).lower()
    matches = sum(1 for term in CATALYST_TERMS if term in text)
    return min(15, matches * 4)


def _row_text(row: dict[str, str]) -> str:
    fields = [
        "theme",
        "current_status",
        "evidence_summary",
        "metric_or_form",
        "concept",
        "label",
        "source_name",
        "review_status",
    ]
    return " ".join(str(row.get(field, "")) for field in fields)


def _int_value(raw: object) -> int:
    try:
        return int(str(raw or "0"))
    except ValueError:
        return 0


def _transition(prior_row: dict[str, str], current_status: str, current_score: int) -> dict[str, object]:
    prior_status = str(prior_row.get("current_status") or prior_row.get("status") or "").strip()
    prior_score = _int_value(prior_row.get("total_score"))
    if not prior_status:
        return {
            "prior_status": "",
            "status_change": "NO_PRIOR",
            "score_delta": 0,
            "newly_promoted": False,
            "newly_downgraded": False,
            "unchanged": False,
        }
    prior_rank = _status_rank(prior_status)
    current_rank = _status_rank(current_status)
    promoted = current_rank < prior_rank
    downgraded = current_rank > prior_rank
    unchanged = current_status == prior_status
    if promoted:
        status_change = "PROMOTED"
    elif downgraded:
        status_change = "DOWNGRADED"
    else:
        status_change = "UNCHANGED"
    return {
        "prior_status": prior_status,
        "status_change": status_change,
        "score_delta": current_score - prior_score,
        "newly_promoted": promoted,
        "newly_downgraded": downgraded,
        "unchanged": unchanged,
    }


def _status_rank(status: str) -> int:
    try:
        return STATUSES.index(status)
    except ValueError:
        return len(STATUSES)


def _unresolved_blockers(
    *,
    warning_codes: set[str],
    valuation_available: bool,
    coverage_status: str,
    risk_penalty: int,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if not valuation_available:
        blockers.append("missing valuation data")
    if WEAK_SOURCE_COVERAGE in warning_codes:
        blockers.append("weak source coverage")
    if MISSING_SOURCE_DATE in warning_codes:
        blockers.append("missing source dates")
    if STALE_EVIDENCE in warning_codes or coverage_status == "STALE":
        blockers.append("stale evidence")
    if risk_penalty >= 35:
        blockers.append("high risk blocker")
    elif risk_penalty:
        blockers.append("risk warning")
    if NO_IMPROVING_GAPS in warning_codes:
        blockers.append("no improving thesis-gap evidence")
    return tuple(blockers)


def _why_this_status(
    *,
    status: str,
    improving: int,
    valuation_available: bool,
    coverage_status: str,
    risk_penalty: int,
    warning_codes: set[str],
) -> str:
    if status == "OPPORTUNITY_REVIEW":
        return "Source coverage, valuation data, and positive thesis-gap evidence are present without risk blockers."
    if status == "THESIS_IMPROVING":
        return "Positive thesis-gap evidence improved, but the queue still requires valuation review before review-candidate status."
    if status == "VALUATION_BLOCKED":
        return "Positive evidence exists, but valuation data is missing."
    if status == "RISK_BLOCKED":
        return "Risk warnings block review-candidate status."
    if status == "EVIDENCE_BLOCKED":
        return "Evidence coverage is missing, stale, weak, or undated."
    if status == "CATALYST_MONITOR":
        return "Catalyst evidence is visible but review-candidate gates are incomplete."
    if improving == 0 or NO_IMPROVING_GAPS in warning_codes:
        return "No positive thesis-gap evidence is strong enough for a review-candidate status."
    if coverage_status != "COVERED":
        return "Source coverage is not strong enough for review-candidate status."
    if not valuation_available:
        return "Valuation data is missing."
    if risk_penalty:
        return "Risk warnings require review before candidate escalation."
    return "Research queue status assigned by deterministic rules."


def _what_would_upgrade(status: str, blockers: tuple[str, ...]) -> str:
    if status == "OPPORTUNITY_REVIEW":
        return "Maintain source coverage, valuation data, positive thesis evidence, and clear risk checks across the next run."
    if not blockers:
        return "Provide stronger dated source evidence and valuation context in a future reviewed artifact."
    return "Resolve blockers: " + "; ".join(blockers) + "."


def _what_would_downgrade(status: str) -> str:
    if status == "OPPORTUNITY_REVIEW":
        return "Missing valuation data, weak or stale source coverage, loss of positive thesis evidence, or new high-risk warnings would downgrade this status."
    return "New high-risk warnings, stale evidence, or weaker thesis-gap evidence would keep or move this lower in the review queue."


def _required_next_evidence(status: str, blockers: tuple[str, ...]) -> str:
    if status == "OPPORTUNITY_REVIEW":
        return "Next run should confirm dated source coverage, valuation data, and absence of high-risk blockers."
    if blockers:
        return "Evidence needed: " + "; ".join(blockers) + "."
    return "Evidence needed: dated source-backed thesis-gap evidence plus valuation context."


def _company_name(company: str, coverage_row: dict[str, str], evidence_rows: list[dict[str, str]]) -> str:
    if coverage_row.get("company_name"):
        return coverage_row["company_name"]
    for row in evidence_rows:
        if row.get("company_name"):
            return row["company_name"]
    return company


def _review_note(status: str) -> str:
    if status == "OPPORTUNITY_REVIEW":
        return "review candidate; not investment advice"
    if status == "THESIS_IMPROVING":
        return "thesis-improving; needs valuation check"
    if status == "VALUATION_BLOCKED":
        return "needs valuation check"
    if status == "CATALYST_MONITOR":
        return "catalyst monitor; review evidence trend"
    if status == "RISK_BLOCKED":
        return "risk review required"
    if status == "EVIDENCE_BLOCKED":
        return "needs dated source coverage"
    return "review queue only"
