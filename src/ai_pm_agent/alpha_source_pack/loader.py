"""Load an explicit Alpha Source Pack path."""

from __future__ import annotations

from pathlib import Path

from .models import AlphaSourcePack
from .validator import (
    AlphaSourcePackValidationError,
    load_json_object,
    load_jsonl,
    load_quality_csv,
    require_pack_file_set,
    resolve_source_pack_path,
    validate_manifest,
    validate_no_forbidden_content,
    validate_records,
)


def load_alpha_source_pack(source_pack: Path | str) -> AlphaSourcePack:
    pack_path = resolve_source_pack_path(Path(source_pack))
    require_pack_file_set(pack_path)
    validate_no_forbidden_content(pack_path)

    manifest = load_json_object(pack_path / "manifest.json")
    validate_manifest(manifest)
    reviewed_signals = load_jsonl(pack_path / "reviewed_signals.jsonl")
    theme_candidates = load_jsonl(pack_path / "theme_candidates.jsonl")
    evidence_manifest = load_jsonl(pack_path / "evidence_manifest.jsonl")
    outcomes = load_jsonl(pack_path / "outcomes.jsonl")
    quality_audit = load_quality_csv(pack_path / "quality_audit.csv")
    red_team_summary = (pack_path / "red_team_summary.md").read_text(encoding="utf-8")
    rejected_noise_summary = (pack_path / "rejected_noise_summary.md").read_text(encoding="utf-8")

    validate_records(
        reviewed_signals=reviewed_signals,
        theme_candidates=theme_candidates,
        evidence_manifest=evidence_manifest,
        outcomes=outcomes,
        quality_audit=quality_audit,
    )
    return AlphaSourcePack(
        source_pack_path=pack_path,
        manifest=manifest,
        reviewed_signals=reviewed_signals,
        theme_candidates=theme_candidates,
        evidence_manifest=evidence_manifest,
        quality_audit=quality_audit,
        outcomes=outcomes,
        red_team_summary=red_team_summary,
        rejected_noise_summary=rejected_noise_summary,
    )


__all__ = ["AlphaSourcePackValidationError", "load_alpha_source_pack"]
