"""Map Alpha source-pack records into review-first opportunity states."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .models import AlphaSourcePack, AlphaSourcePackImportResult, EvidenceProvenance, ImportedAlphaItem


BLOCKING_CLASSIFICATIONS = ("overclaimed", "needs score cap", "needs wording downgrade")
CATALYST_TERMS = ("catalyst", "reaction", "earnings", "rewarded")
VALUATION_TERMS = ("valuation", "multiple", "dcf", "discounted cash flow", "price target", "downside case")
PORTFOLIO_CONTEXT_TERMS = ("portfolio context", "position size", "target weight", "portfolio exposure")

REASON_TEXT = {
    "SOURCE_REJECTED_NOISE": "Source Alpha record is rejected/noise.",
    "NOT_MANUALLY_REVIEWED": "Source Alpha record is not manually reviewed.",
    "MISSING_EVIDENCE": "Source Alpha record still lists missing evidence.",
    "QUALITY_AUDIT_BLOCKER": "Quality audit blocks import promotion.",
    "QUALITY_AUDIT_ISSUES": "Quality audit lists unresolved issues.",
    "VALUATION_EVIDENCE_MISSING": "Valuation evidence is required before PM-facing thesis improvement.",
    "PORTFOLIO_CONTEXT_REQUIRED_NOT_USED": "Portfolio context would be required but was not used by this importer.",
    "REVIEWED_WATCH_ONLY": "Reviewed Watch source remains watchlist-only.",
    "REVIEWED_INCUBATING": "Reviewed Incubating source passed basic import gates.",
    "QUALITY_AUDIT_PASSED": "Quality audit has no blocking issues or missing evidence.",
    "CATALYST_LANGUAGE": "Reviewed Incubating source is catalyst or event-monitor oriented.",
    "IMPORT_RULE_FALLBACK": "Source record did not meet a higher-confidence import rule.",
}


def map_alpha_source_pack(pack: AlphaSourcePack) -> AlphaSourcePackImportResult:
    imported_signals = tuple(_map_signal(pack, signal) for signal in pack.reviewed_signals)
    imported_candidates = tuple(_map_candidate(pack, candidate) for candidate in pack.theme_candidates)
    counts = Counter(item.opportunity_state for item in imported_signals + imported_candidates)
    return AlphaSourcePackImportResult(
        source_pack_path=pack.source_pack_path,
        imported_signals=imported_signals,
        imported_candidates=imported_candidates,
        state_counts=dict(sorted(counts.items())),
    )


def _map_signal(pack: AlphaSourcePack, signal: dict[str, Any]) -> ImportedAlphaItem:
    audit = pack.quality_by_signal_id.get(signal["id"], {})
    classification = audit.get("classification", "")
    missing = _split_semicolonish(audit.get("missing_evidence", ""))
    issues = _split_semicolonish(audit.get("issues", ""))
    context_values = [
        classification,
        audit.get("confidence_cap_reason", ""),
        signal.get("title", ""),
        signal.get("summary", ""),
        *missing,
        *issues,
    ]
    valuation_required = _contains_any(context_values, VALUATION_TERMS)
    portfolio_context_required = _contains_any(context_values, PORTFOLIO_CONTEXT_TERMS)
    title_text = signal.get("title", "").lower()

    if signal["status"] in {"Noise", "Rejected"}:
        state = "DO_NOT_USE"
        reason_codes = ["SOURCE_REJECTED_NOISE"]
    elif valuation_required:
        state = "VALUATION_BLOCKED"
        reason_codes = ["VALUATION_EVIDENCE_MISSING"]
        if missing:
            reason_codes.append("MISSING_EVIDENCE")
    elif portfolio_context_required:
        state = "EVIDENCE_BLOCKED"
        reason_codes = ["PORTFOLIO_CONTEXT_REQUIRED_NOT_USED"]
        if missing:
            reason_codes.append("MISSING_EVIDENCE")
    elif _has_quality_blocker(classification, issues, missing):
        state = "EVIDENCE_BLOCKED"
        reason_codes = _quality_blocker_reason_codes(classification, issues, missing)
    elif signal["status"] == "Watch":
        state = "WATCHLIST_ONLY"
        reason_codes = ["REVIEWED_WATCH_ONLY"]
    elif signal["status"] == "Incubating" and signal["review_status"] == "reviewed":
        state = "CATALYST_MONITOR" if any(term in title_text for term in CATALYST_TERMS) else "THESIS_IMPROVING"
        reason_codes = ["REVIEWED_INCUBATING", "QUALITY_AUDIT_PASSED"]
        if state == "CATALYST_MONITOR":
            reason_codes.append("CATALYST_LANGUAGE")
    else:
        state = "EVIDENCE_BLOCKED"
        reason_codes = ["IMPORT_RULE_FALLBACK"]

    return ImportedAlphaItem(
        source_id=signal["id"],
        source_kind="signal",
        title=signal["title"],
        opportunity_state=state,
        source_status=signal["status"],
        review_status=signal["review_status"],
        source_refs=tuple(signal.get("source_refs", [])),
        evidence_provenance=_provenance(pack, signal.get("source_refs", [])),
        evidence_quality=_evidence_quality(pack, signal.get("source_refs", [])),
        quality_classification=classification,
        missing_evidence=tuple(missing),
        red_team_objection=signal.get("red_team_objection", ""),
        what_would_upgrade=signal.get("what_would_confirm", ""),
        what_would_downgrade=signal.get("what_would_falsify", ""),
        mapping_reason=_mapping_reason(reason_codes),
        mapping_reason_codes=tuple(reason_codes),
        valuation_required=valuation_required,
        portfolio_context_required_but_not_used=portfolio_context_required,
    )


def _map_candidate(pack: AlphaSourcePack, candidate: dict[str, Any]) -> ImportedAlphaItem:
    missing = list(candidate.get("missing_evidence") or [])
    context_values = [
        candidate.get("theme_name", ""),
        candidate.get("summary", ""),
        candidate.get("red_team_objection", ""),
        candidate.get("what_would_confirm", ""),
        candidate.get("what_would_falsify", ""),
        *missing,
    ]
    valuation_required = _contains_any(context_values, VALUATION_TERMS)
    portfolio_context_required = _contains_any(context_values, PORTFOLIO_CONTEXT_TERMS)
    if candidate["status"] in {"Noise", "Rejected"} or candidate["review_status"] == "rejected":
        state = "DO_NOT_USE"
        reason_codes = ["SOURCE_REJECTED_NOISE"]
    elif candidate["review_status"] != "reviewed":
        state = "EVIDENCE_BLOCKED"
        reason_codes = ["NOT_MANUALLY_REVIEWED"]
        if missing:
            reason_codes.append("MISSING_EVIDENCE")
    elif valuation_required:
        state = "VALUATION_BLOCKED"
        reason_codes = ["VALUATION_EVIDENCE_MISSING"]
        if missing:
            reason_codes.append("MISSING_EVIDENCE")
    elif portfolio_context_required:
        state = "EVIDENCE_BLOCKED"
        reason_codes = ["PORTFOLIO_CONTEXT_REQUIRED_NOT_USED"]
        if missing:
            reason_codes.append("MISSING_EVIDENCE")
    elif missing:
        state = "EVIDENCE_BLOCKED"
        reason_codes = ["MISSING_EVIDENCE"]
    elif candidate["status"] == "Watch":
        state = "WATCHLIST_ONLY"
        reason_codes = ["REVIEWED_WATCH_ONLY"]
    elif candidate["status"] == "Incubating":
        state = "THESIS_IMPROVING"
        reason_codes = ["REVIEWED_INCUBATING", "QUALITY_AUDIT_PASSED"]
    else:
        state = "EVIDENCE_BLOCKED"
        reason_codes = ["IMPORT_RULE_FALLBACK"]

    return ImportedAlphaItem(
        source_id=candidate["candidate_id"],
        source_kind="theme_candidate",
        title=candidate["theme_name"],
        opportunity_state=state,
        source_status=candidate["status"],
        review_status=candidate["review_status"],
        source_refs=tuple(candidate.get("evidence_refs", [])),
        evidence_provenance=_provenance(pack, candidate.get("evidence_refs", [])),
        evidence_quality=_evidence_quality(pack, candidate.get("evidence_refs", [])),
        missing_evidence=tuple(missing),
        red_team_objection=candidate.get("red_team_objection", ""),
        what_would_upgrade=candidate.get("what_would_confirm", ""),
        what_would_downgrade=candidate.get("what_would_falsify", ""),
        mapping_reason=_mapping_reason(reason_codes),
        mapping_reason_codes=tuple(reason_codes),
        valuation_required=valuation_required,
        portfolio_context_required_but_not_used=portfolio_context_required,
    )


def _has_quality_blocker(classification: str, issues: list[str], missing: list[str]) -> bool:
    normalized = classification.lower()
    if any(term in normalized for term in BLOCKING_CLASSIFICATIONS):
        return True
    if missing:
        return True
    return bool(issues and "acceptable" not in normalized)


def _quality_blocker_reason_codes(classification: str, issues: list[str], missing: list[str]) -> list[str]:
    codes: list[str] = []
    normalized = classification.lower()
    if any(term in normalized for term in BLOCKING_CLASSIFICATIONS):
        codes.append("QUALITY_AUDIT_BLOCKER")
    if missing:
        codes.append("MISSING_EVIDENCE")
    if issues and "acceptable" not in normalized:
        codes.append("QUALITY_AUDIT_ISSUES")
    return codes or ["QUALITY_AUDIT_BLOCKER"]


def _contains_any(values: list[str], terms: tuple[str, ...]) -> bool:
    haystack = " ".join(value for value in values if value).lower()
    return any(term in haystack for term in terms)


def _mapping_reason(codes: list[str]) -> str:
    return " ".join(REASON_TEXT.get(code, code) for code in codes)


def _split_semicolonish(value: str) -> list[str]:
    if not value:
        return []
    parts = []
    for chunk in value.replace("|", ";").split(";"):
        item = chunk.strip()
        if item:
            parts.append(item)
    return parts


def _provenance(pack: AlphaSourcePack, refs: list[str]) -> tuple[EvidenceProvenance, ...]:
    evidence_by_id = pack.evidence_by_id
    return tuple(
        EvidenceProvenance.from_record(evidence_by_id[ref])
        for ref in refs
        if ref in evidence_by_id
    )


def _evidence_quality(pack: AlphaSourcePack, refs: list[str]) -> str:
    provenances = _provenance(pack, refs)
    if not provenances:
        return "missing"
    statuses = {item.review_status for item in provenances}
    reliabilities = {item.reliability for item in provenances}
    return f"reviews={','.join(sorted(statuses))}; reliability={','.join(sorted(reliabilities))}"
