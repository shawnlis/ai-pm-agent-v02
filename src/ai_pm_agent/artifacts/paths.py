"""Path discovery for existing AI PM Agent research artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


RUN_MARKER = "pm_decision.json"

KNOWN_RUN_ARTIFACTS = (
    "pm_decision.json",
    "market_snapshot.json",
    "quality_report.md",
    "market_snapshot.md",
    "evidence_context.md",
    "fact_cache_report_before.json",
    "fact_cache_report_before.md",
    "fact_cache_report_after.json",
    "fact_cache_report_after.md",
    "cached_facts_used.json",
    "fresh_facts.json",
)

OPTIONAL_RUN_ARTIFACTS = tuple(name for name in KNOWN_RUN_ARTIFACTS if name != RUN_MARKER)

FACT_ARTIFACTS = ("cached_facts_used.json", "fresh_facts.json")


@dataclass(frozen=True)
class ResearchRunPaths:
    """Resolved paths for a single artifact run folder."""

    artifact_dir: Path
    pm_decision: Path
    files: tuple[Path, ...]


def discover_research_runs(outputs_dir: Path | str, limit: int | None = None) -> list[ResearchRunPaths]:
    """Find run folders by locating pm_decision.json under outputs_dir."""

    root = Path(outputs_dir)
    if not root.exists():
        return []

    run_dirs = sorted({path.parent for path in root.rglob(RUN_MARKER)}, key=_path_sort_key)
    if limit is not None:
        run_dirs = run_dirs[:limit]
    return [build_research_run_paths(path) for path in run_dirs]


def build_research_run_paths(run_dir: Path | str) -> ResearchRunPaths:
    """Build a run-path bundle from a known run directory."""

    artifact_dir = Path(run_dir)
    files = tuple(artifact_dir / name for name in KNOWN_RUN_ARTIFACTS if (artifact_dir / name).exists())
    return ResearchRunPaths(
        artifact_dir=artifact_dir,
        pm_decision=artifact_dir / RUN_MARKER,
        files=files,
    )


def iter_present_known_files(run_dir: Path | str) -> Iterable[Path]:
    """Yield known artifact files that are present in a run directory."""

    artifact_dir = Path(run_dir)
    for name in KNOWN_RUN_ARTIFACTS:
        path = artifact_dir / name
        if path.exists():
            yield path


def artifact_type_for(path: Path | str) -> str:
    """Return a compact artifact type label for known files."""

    name = Path(path).name
    if name == "pm_decision.json":
        return "pm_decision_json"
    if name == "market_snapshot.json":
        return "market_snapshot_json"
    if name == "quality_report.md":
        return "quality_report_markdown"
    if name == "market_snapshot.md":
        return "market_snapshot_markdown"
    if name == "evidence_context.md":
        return "evidence_context_markdown"
    if name.startswith("fact_cache_report_") and name.endswith(".json"):
        return "fact_cache_report_json"
    if name.startswith("fact_cache_report_") and name.endswith(".md"):
        return "fact_cache_report_markdown"
    if name in FACT_ARTIFACTS:
        return "facts_json"
    if name == "research_log.csv":
        return "research_log_csv"
    return "unknown"


def relative_to_or_abs(path: Path | str, root: Path | str | None) -> str:
    """Return path relative to root when possible, otherwise absolute text."""

    target = Path(path)
    if root is None:
        return str(target)
    try:
        return str(target.resolve().relative_to(Path(root).resolve()))
    except ValueError:
        return str(target.resolve())


def _path_sort_key(path: Path) -> str:
    return str(path).lower()
