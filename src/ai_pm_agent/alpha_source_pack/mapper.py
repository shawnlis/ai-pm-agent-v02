"""Map Alpha source-pack records into review-first opportunity states."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .models import AlphaSourcePack, AlphaSourcePackImportResult, EvidenceProvenance, ImportedAlphaItem


BLOCKING_CLASSIFICATIONS = ("overclaimed", "needs score cap", "needs wording downgrade")
CATALYST_TERMS = ("catalyst", "reaction", "earnings", "rewarded")


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
    title_text = f"{signal.get('title', '')} {signal.get('summary', '')}".lower()

    if signal["status"] in {"Noise", "Rejected"}:
        state = "DO_NOT_USE"
        reason = "Signal source status is rejected/noise."
    elif _has_quality_blocker(classification, issues, missing):
        state = "EVIDENCE_BLOCKED"
        reason = "Quality audit flags overclaiming or missing evidence."
    elif signal["status"] == "Watch":
        state = "WATCHLIST_ONLY"
        reason = "Reviewed Watch signal remains review-only."
    elif signal["status"] == "Incubating" and signal["review_status"] == "reviewed":
        state = "CATALYST_MONITOR" if any(term in title_text for term in CATALYST_TERMS) else "THESIS_IMPROVING"
        reason = "Reviewed Incubating signal passed quality gate."
    else:
        state = "EVIDENCE_BLOCKED"
        reason = "Signal did not meet import promotion rules."

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
        mapping_reason=reason,
    )


def _map_candidate(pack: AlphaSourcePack, candidate: dict[str, Any]) -> ImportedAlphaItem:
    missing = list(candidate.get("missing_evidence") or [])
    if candidate["status"] in {"Noise", "Rejected"} or candidate["review_status"] == "rejected":
        state = "DO_NOT_USE"
        reason = "Theme candidate was rejected/noise."
    elif candidate["review_status"] != "reviewed":
        state = "EVIDENCE_BLOCKED"
        reason = "Theme candidate is not manually reviewed."
    elif missing:
        state = "EVIDENCE_BLOCKED"
        reason = "Theme candidate still lists missing evidence."
    elif candidate["status"] == "Watch":
        state = "WATCHLIST_ONLY"
        reason = "Reviewed Watch candidate remains watchlist-only."
    elif candidate["status"] == "Incubating":
        state = "THESIS_IMPROVING"
        reason = "Reviewed Incubating candidate has no listed missing evidence."
    else:
        state = "EVIDENCE_BLOCKED"
        reason = "Theme candidate did not meet import rules."

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
        mapping_reason=reason,
    )


def _has_quality_blocker(classification: str, issues: list[str], missing: list[str]) -> bool:
    normalized = classification.lower()
    if any(term in normalized for term in BLOCKING_CLASSIFICATIONS):
        return True
    if missing:
        return True
    return bool(issues and "acceptable" not in normalized)


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
