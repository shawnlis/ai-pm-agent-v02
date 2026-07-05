"""Models for read-only Alpha Source Pack imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PACK_FILES = {
    "manifest.json",
    "reviewed_signals.jsonl",
    "theme_candidates.jsonl",
    "evidence_manifest.jsonl",
    "quality_audit.csv",
    "outcomes.jsonl",
    "red_team_summary.md",
    "rejected_noise_summary.md",
}

OPPORTUNITY_STATES = {
    "WATCHLIST_ONLY",
    "EVIDENCE_BLOCKED",
    "VALUATION_BLOCKED",
    "THESIS_IMPROVING",
    "CATALYST_MONITOR",
    "DO_NOT_USE",
}

REVIEW_FIRST_BOUNDARY = {
    "mode": "review_first",
    "autopm_enabled": False,
    "portfolio_context_used": False,
    "broker_connection": False,
    "execution_enabled": False,
    "pm_decision_engine": False,
}


@dataclass(frozen=True)
class AlphaSourcePack:
    source_pack_path: Path
    manifest: dict[str, Any]
    reviewed_signals: list[dict[str, Any]]
    theme_candidates: list[dict[str, Any]]
    evidence_manifest: list[dict[str, Any]]
    quality_audit: list[dict[str, str]]
    outcomes: list[dict[str, Any]]
    red_team_summary: str
    rejected_noise_summary: str

    @property
    def evidence_by_id(self) -> dict[str, dict[str, Any]]:
        return {record["id"]: record for record in self.evidence_manifest}

    @property
    def quality_by_signal_id(self) -> dict[str, dict[str, str]]:
        return {record["signal_id"]: record for record in self.quality_audit}


@dataclass(frozen=True)
class EvidenceProvenance:
    evidence_id: str
    source_type: str
    source_name: str
    reliability: str
    review_status: str
    source_reference: str | None

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "EvidenceProvenance":
        return cls(
            evidence_id=record["id"],
            source_type=record["source_type"],
            source_name=record["source_name"],
            reliability=record["reliability"],
            review_status=record["review_status"],
            source_reference=record.get("source_reference"),
        )


@dataclass(frozen=True)
class ImportedAlphaItem:
    source_id: str
    source_kind: str
    title: str
    opportunity_state: str
    source_status: str
    review_status: str
    source_refs: tuple[str, ...]
    evidence_provenance: tuple[EvidenceProvenance, ...]
    evidence_quality: str
    quality_classification: str = ""
    missing_evidence: tuple[str, ...] = field(default_factory=tuple)
    red_team_objection: str = ""
    what_would_upgrade: str = ""
    what_would_downgrade: str = ""
    mapping_reason: str = ""
    mapping_reason_codes: tuple[str, ...] = field(default_factory=tuple)
    valuation_required: bool = False
    portfolio_context_required_but_not_used: bool = False
    current_blocker: str = ""
    exact_missing_evidence: tuple[str, ...] = field(default_factory=tuple)
    required_for_THESIS_IMPROVING: tuple[str, ...] = field(default_factory=tuple)
    required_for_CATALYST_MONITOR: tuple[str, ...] = field(default_factory=tuple)
    required_for_OPPORTUNITY_REVIEW: tuple[str, ...] = field(default_factory=tuple)
    valuation_gap: str = ""
    portfolio_gap_not_used: str = ""
    red_team_blocker: str = ""

    @property
    def source_alpha_status(self) -> str:
        return self.source_status

    @property
    def mapped_ai_pm_status(self) -> str:
        return self.opportunity_state

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "title": self.title,
            "opportunity_state": self.opportunity_state,
            "source_status": self.source_status,
            "source_alpha_status": self.source_alpha_status,
            "mapped_ai_pm_status": self.mapped_ai_pm_status,
            "review_status": self.review_status,
            "source_refs": list(self.source_refs),
            "evidence_provenance": [provenance.__dict__ for provenance in self.evidence_provenance],
            "evidence_quality": self.evidence_quality,
            "quality_classification": self.quality_classification,
            "missing_evidence": list(self.missing_evidence),
            "red_team_objection": self.red_team_objection,
            "what_would_upgrade": self.what_would_upgrade,
            "what_would_downgrade": self.what_would_downgrade,
            "mapping_reason": self.mapping_reason,
            "mapping_reason_codes": list(self.mapping_reason_codes),
            "valuation_required": self.valuation_required,
            "portfolio_context_required_but_not_used": self.portfolio_context_required_but_not_used,
            "current_blocker": self.current_blocker,
            "exact_missing_evidence": list(self.exact_missing_evidence),
            "required_for_THESIS_IMPROVING": list(self.required_for_THESIS_IMPROVING),
            "required_for_CATALYST_MONITOR": list(self.required_for_CATALYST_MONITOR),
            "required_for_OPPORTUNITY_REVIEW": list(self.required_for_OPPORTUNITY_REVIEW),
            "valuation_gap": self.valuation_gap,
            "portfolio_gap_not_used": self.portfolio_gap_not_used,
            "red_team_blocker": self.red_team_blocker,
        }


@dataclass(frozen=True)
class AlphaSourcePackImportResult:
    source_pack_path: Path
    imported_signals: tuple[ImportedAlphaItem, ...]
    imported_candidates: tuple[ImportedAlphaItem, ...]
    state_counts: dict[str, int]
    boundary: dict[str, bool | str] = field(default_factory=lambda: dict(REVIEW_FIRST_BOUNDARY))

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_pack_path": str(self.source_pack_path),
            "imported_signals": [item.as_dict() for item in self.imported_signals],
            "imported_candidates": [item.as_dict() for item in self.imported_candidates],
            "state_counts": self.state_counts,
            "boundary": self.boundary,
        }
