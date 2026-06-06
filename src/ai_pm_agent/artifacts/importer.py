"""Import existing AI PM Agent artifacts into the company research database."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ai_pm_agent.artifacts.paths import (
    FACT_ARTIFACTS,
    OPTIONAL_RUN_ARTIFACTS,
    ResearchRunPaths,
    artifact_type_for,
    discover_research_runs,
    iter_present_known_files,
    relative_to_or_abs,
)
from ai_pm_agent.company_db.migrations import utc_now
from ai_pm_agent.company_db.repository import CompanyResearchRepository


@dataclass(frozen=True)
class ImportWarning:
    warning_type: str
    message: str
    artifact_path: str | None = None


@dataclass
class RunImportResult:
    run_id: str
    artifact_dir: str
    status: str
    imported_files: int = 0
    evidence_items: int = 0
    facts: int = 0
    warnings: list[ImportWarning] = field(default_factory=list)


@dataclass
class ImportSummary:
    outputs_dir: str
    db_path: str
    dry_run: bool
    discovered: int
    imported: int
    would_import: int
    skipped: int
    warnings: int
    results: list[RunImportResult]


class CompanyDbImporter:
    """Importer for local output artifacts produced by ai_pm_agent.py."""

    def __init__(self, outputs_dir: Path | str, db_path: Path | str, limit: int | None = None):
        self.outputs_dir = Path(outputs_dir)
        self.db_path = Path(db_path)
        self.limit = limit
        self.research_log_path = self.outputs_dir / "research_log.csv"
        self.research_log_rows, self.research_log_index = self._load_research_log()

    def import_outputs(self, dry_run: bool = False) -> ImportSummary:
        runs = discover_research_runs(self.outputs_dir, self.limit)
        results: list[RunImportResult] = []

        if dry_run:
            for run_paths in runs:
                results.append(self._process_run(run_paths, repo=None, dry_run=True))
        else:
            with CompanyResearchRepository(self.db_path) as repo:
                for run_paths in runs:
                    results.append(self._process_run(run_paths, repo=repo, dry_run=False))
                repo.commit()

        imported = 0 if dry_run else sum(1 for result in results if result.status.startswith("imported"))
        would_import = sum(1 for result in results if result.status.startswith("would_import"))
        skipped = sum(1 for result in results if result.status.startswith("skipped"))
        warning_count = sum(len(result.warnings) for result in results)
        return ImportSummary(
            outputs_dir=str(self.outputs_dir),
            db_path=str(self.db_path),
            dry_run=dry_run,
            discovered=len(runs),
            imported=imported,
            would_import=would_import,
            skipped=skipped,
            warnings=warning_count,
            results=results,
        )

    def _process_run(
        self,
        run_paths: ResearchRunPaths,
        repo: CompanyResearchRepository | None,
        dry_run: bool,
    ) -> RunImportResult:
        warnings: list[ImportWarning] = []
        now = utc_now()
        run_dir = run_paths.artifact_dir
        run_id = stable_id("run", _normalize_path(run_dir))

        for artifact_name in OPTIONAL_RUN_ARTIFACTS:
            path = run_dir / artifact_name
            if not path.exists():
                warnings.append(
                    ImportWarning(
                        "missing_optional_artifact",
                        f"Optional artifact is missing: {artifact_name}",
                        str(path),
                    )
                )

        pm_decision, pm_raw = self._read_json(run_paths.pm_decision, warnings, "pm_decision_json")
        if pm_decision is not None and not isinstance(pm_decision, dict):
            warnings.append(
                ImportWarning(
                    "invalid_json_shape",
                    "pm_decision.json did not contain a JSON object",
                    str(run_paths.pm_decision),
                )
            )
            pm_decision = None

        market_path = run_dir / "market_snapshot.json"
        market_snapshot: dict[str, Any] | None = None
        market_raw: str | None = None
        if market_path.exists():
            market_obj, market_raw = self._read_json(market_path, warnings, "market_snapshot_json")
            if isinstance(market_obj, dict):
                market_snapshot = market_obj
            elif market_obj is not None:
                warnings.append(
                    ImportWarning(
                        "invalid_json_shape",
                        "market_snapshot.json did not contain a JSON object",
                        str(market_path),
                    )
                )

        folder_ticker, folder_created_at = parse_run_folder(run_dir.name)
        research_log_row = self.research_log_index.get(_normalize_path(run_dir))
        if self.research_log_path.exists() and research_log_row is None:
            warnings.append(
                ImportWarning(
                    "research_log_unmatched",
                    "research_log.csv exists but no row clearly matched this run folder",
                    str(self.research_log_path),
                )
            )

        pm_dict = pm_decision or {}
        market_dict = market_snapshot or {}
        ticker = (
            text_or_none(_pick(pm_dict, "ticker", "symbol"))
            or text_or_none(_pick(market_dict, "ticker", "symbol"))
            or text_or_none(research_log_row.get("ticker") if research_log_row else None)
            or folder_ticker
        )
        ticker = ticker.upper() if ticker else None
        company_name = (
            text_or_none(_pick(pm_dict, "company_name", "company", "name"))
            or text_or_none(_pick(market_dict, "long_name", "short_name", "company_name"))
            or text_or_none(research_log_row.get("company_name") if research_log_row else None)
            or ticker
            or run_dir.name
        )
        market = (
            text_or_none(_pick(pm_dict, "market"))
            or text_or_none(_pick(market_dict, "market"))
            or text_or_none(research_log_row.get("market") if research_log_row else None)
            or ""
        )
        theme = (
            text_or_none(_pick(pm_dict, "theme"))
            or text_or_none(research_log_row.get("theme") if research_log_row else None)
        )
        run_created_at = (
            text_or_none(_pick(pm_dict, "created_at", "run_created_at"))
            or text_or_none(research_log_row.get("created_at") if research_log_row else None)
            or folder_created_at
            or file_mtime_iso(run_paths.pm_decision)
        )

        evidence_rows = self._build_evidence_rows(run_id, run_dir, warnings, now)
        fact_rows = self._build_fact_rows(run_id, run_dir, warnings, now)
        present_files = list(iter_present_known_files(run_dir))
        if research_log_row is not None and self.research_log_path.exists():
            present_files.append(self.research_log_path)

        status_prefix = "would_import" if dry_run else "imported"
        status = f"{status_prefix}_with_warnings" if warnings else status_prefix

        if repo is not None:
            canonical_name = company_name.strip()
            company_id = stable_id("company", canonical_name.lower())
            ticker_id = stable_id("ticker", ticker or "", market or "") if ticker else None

            repo.upsert_company(
                {
                    "company_id": company_id,
                    "canonical_name": canonical_name,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            if ticker:
                repo.upsert_ticker(
                    {
                        "ticker_id": ticker_id,
                        "company_id": company_id,
                        "ticker": ticker,
                        "ticker_norm": ticker.upper(),
                        "market": market or "",
                        "financial_ticker": text_or_none(_pick(market_dict, "financial_ticker")),
                        "created_at": now,
                        "updated_at": now,
                    }
                )

            repo.upsert_research_run(
                {
                    "run_id": run_id,
                    "artifact_dir": str(run_dir.resolve()),
                    "artifact_dir_rel": relative_to_or_abs(run_dir, self.outputs_dir),
                    "ticker_id": ticker_id,
                    "company_id": company_id,
                    "ticker": ticker,
                    "company_name": canonical_name,
                    "market": market,
                    "theme": theme,
                    "run_created_at": run_created_at,
                    "imported_at": now,
                    "source_modified_at": file_mtime_iso(run_paths.pm_decision),
                    "pm_decision_path": str(run_paths.pm_decision.resolve()),
                    "status": status.replace("would_import", "imported"),
                    "research_log_row_json": dump_json(research_log_row) if research_log_row else None,
                    "raw_metadata_json": dump_json(
                        {
                            "folder_name": run_dir.name,
                            "files_seen": [path.name for path in present_files],
                            "source": "local_outputs_importer",
                        }
                    ),
                }
            )

            for path in present_files:
                repo.upsert_artifact_file(self._artifact_file_row(run_id, path, now))

            if pm_decision is not None and pm_raw is not None:
                repo.upsert_pm_decision(self._pm_decision_row(run_id, pm_decision, pm_raw, now))
                repo.upsert_chokepoint_assessment(
                    self._chokepoint_assessment_row(run_id, pm_decision, now)
                )
            if market_snapshot is not None and market_raw is not None:
                repo.upsert_market_snapshot(
                    self._market_snapshot_row(run_id, market_snapshot, market_raw, now)
                )

            repo.replace_evidence_items(run_id, "evidence_context.md", evidence_rows)
            for source_file, rows in group_rows_by_source_file(fact_rows).items():
                repo.replace_facts(run_id, source_file, rows)

            for warning in warnings:
                repo.add_warning(
                    {
                        "warning_id": stable_id(
                            "warning",
                            run_id,
                            warning.artifact_path or "",
                            warning.warning_type,
                            warning.message,
                        ),
                        "run_id": run_id,
                        "artifact_path": warning.artifact_path,
                        "warning_type": warning.warning_type,
                        "message": warning.message,
                        "created_at": now,
                    }
                )

        return RunImportResult(
            run_id=run_id,
            artifact_dir=str(run_dir),
            status=status,
            imported_files=len(present_files),
            evidence_items=len(evidence_rows),
            facts=len(fact_rows),
            warnings=warnings,
        )

    def _build_evidence_rows(
        self,
        run_id: str,
        run_dir: Path,
        warnings: list[ImportWarning],
        imported_at: str,
    ) -> list[dict[str, Any]]:
        path = run_dir / "evidence_context.md"
        if not path.exists():
            return []
        text = self._read_text(path, warnings, "evidence_context_markdown")
        if text is None:
            return []
        parsed = parse_evidence_context(text)
        rows = []
        for ordinal, item in enumerate(parsed, start=1):
            rows.append(
                {
                    "evidence_id": stable_id("evidence", run_id, path.name, ordinal),
                    "run_id": run_id,
                    "source_file": path.name,
                    "ordinal": ordinal,
                    "provider": item.get("provider"),
                    "query_type": item.get("query_type"),
                    "expected_tier": item.get("expected_tier"),
                    "evidence_tier": item.get("evidence_tier"),
                    "source_type": item.get("source_type"),
                    "source_domain": item.get("source_domain"),
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "snippet": item.get("snippet"),
                    "raw_text": item.get("raw_text"),
                    "imported_at": imported_at,
                }
            )
        return rows

    def _build_fact_rows(
        self,
        run_id: str,
        run_dir: Path,
        warnings: list[ImportWarning],
        imported_at: str,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for file_name in FACT_ARTIFACTS:
            path = run_dir / file_name
            if not path.exists():
                continue
            obj, _raw = self._read_json(path, warnings, "facts_json")
            facts = extract_fact_records(obj)
            if obj is not None and not facts:
                warnings.append(
                    ImportWarning(
                        "facts_parse_empty",
                        "Facts JSON was present but no fact records were found",
                        str(path),
                    )
                )
            for ordinal, fact in enumerate(facts, start=1):
                rows.append(
                    {
                        "fact_id": stable_id("fact", run_id, file_name, ordinal),
                        "run_id": run_id,
                        "source_file": file_name,
                        "ordinal": ordinal,
                        "ticker": text_or_none(fact.get("ticker")),
                        "company_name": text_or_none(fact.get("company_name")),
                        "theme": text_or_none(fact.get("theme")),
                        "market": text_or_none(fact.get("market")),
                        "fact": text_or_none(fact.get("fact")),
                        "fact_category": text_or_none(fact.get("fact_category")),
                        "source_url": text_or_none(fact.get("source_url")),
                        "source_domain": text_or_none(fact.get("source_domain")),
                        "evidence_tier": text_or_none(fact.get("evidence_tier")),
                        "source_type": text_or_none(fact.get("source_type")),
                        "title": text_or_none(fact.get("title")),
                        "snippet": text_or_none(fact.get("snippet")),
                        "confidence": to_float(fact.get("confidence")),
                        "query_type": text_or_none(fact.get("query_type")),
                        "provider": text_or_none(fact.get("provider")),
                        "model_used": text_or_none(fact.get("model_used")),
                        "fetched_at": text_or_none(fact.get("fetched_at") or fact.get("created_at")),
                        "source_published_at": text_or_none(fact.get("source_published_at")),
                        "expires_at": text_or_none(fact.get("expires_at")),
                        "raw_json": dump_json(fact),
                        "imported_at": imported_at,
                    }
                )
        return rows

    def _artifact_file_row(self, run_id: str, path: Path, imported_at: str) -> dict[str, Any]:
        return {
            "artifact_file_id": stable_id("artifact", run_id, _normalize_path(path)),
            "run_id": run_id,
            "artifact_path": str(path.resolve()),
            "artifact_path_rel": relative_to_or_abs(path, self.outputs_dir),
            "file_type": artifact_type_for(path),
            "sha256": sha256_file(path),
            "size_bytes": file_size(path),
            "modified_at": file_mtime_iso(path),
            "imported_at": imported_at,
        }

    def _pm_decision_row(
        self,
        run_id: str,
        pm_decision: dict[str, Any],
        raw_json: str,
        imported_at: str,
    ) -> dict[str, Any]:
        return {
            "decision_id": stable_id("pm_decision", run_id),
            "run_id": run_id,
            "ticker": text_or_none(_pick(pm_decision, "ticker", "symbol")),
            "company_name": text_or_none(_pick(pm_decision, "company_name", "company", "name")),
            "rating": text_or_none(_pick(pm_decision, "rating")),
            "action": text_or_none(_pick(pm_decision, "action")),
            "suggested_position_pct": to_float(_pick(pm_decision, "suggested_position_pct")),
            "confidence_score": to_float(_pick(pm_decision, "confidence_score")),
            "risk_score": to_float(_pick(pm_decision, "risk_score")),
            "evidence_quality_score": to_float(_pick(pm_decision, "evidence_quality_score")),
            "valuation_attractiveness_score": to_float(
                _pick(pm_decision, "valuation_attractiveness_score")
            ),
            "weighted_investment_score": to_float(_pick(pm_decision, "weighted_investment_score")),
            "chokepoint_adjusted_score": to_float(_pick(pm_decision, "chokepoint_adjusted_score")),
            "thesis_summary": text_or_none(_pick(pm_decision, "thesis_summary")),
            "final_pm_judgment": text_or_none(_pick(pm_decision, "final_pm_judgment")),
            "valuation_view": text_or_none(_pick(pm_decision, "valuation_view")),
            "valuation_is_justified": to_int_bool(_pick(pm_decision, "valuation_is_justified")),
            "raw_json": raw_json,
            "imported_at": imported_at,
        }

    def _market_snapshot_row(
        self,
        run_id: str,
        snapshot: dict[str, Any],
        raw_json: str,
        imported_at: str,
    ) -> dict[str, Any]:
        return {
            "snapshot_id": stable_id("market_snapshot", run_id),
            "run_id": run_id,
            "ticker": text_or_none(_pick(snapshot, "ticker", "symbol")),
            "financial_ticker": text_or_none(_pick(snapshot, "financial_ticker")),
            "short_name": text_or_none(_pick(snapshot, "short_name")),
            "long_name": text_or_none(_pick(snapshot, "long_name")),
            "sector": text_or_none(_pick(snapshot, "sector")),
            "industry": text_or_none(_pick(snapshot, "industry")),
            "country": text_or_none(_pick(snapshot, "country")),
            "currency": text_or_none(_pick(snapshot, "currency")),
            "financial_currency": text_or_none(_pick(snapshot, "financial_currency")),
            "latest_price": to_float(_pick(snapshot, "latest_price", "current_price")),
            "market_cap": to_float(_pick(snapshot, "market_cap")),
            "enterprise_value": to_float(_pick(snapshot, "enterprise_value")),
            "trailing_pe": to_float(_pick(snapshot, "trailing_pe")),
            "forward_pe": to_float(_pick(snapshot, "forward_pe")),
            "price_to_sales": to_float(_pick(snapshot, "price_to_sales", "price_to_sales_ttm")),
            "price_to_book": to_float(_pick(snapshot, "price_to_book")),
            "ev_to_revenue": to_float(_pick(snapshot, "ev_to_revenue")),
            "ev_to_ebitda": to_float(_pick(snapshot, "ev_to_ebitda")),
            "one_year_return": to_float(_pick(snapshot, "one_year_return", "return_1y")),
            "volatility_1y": to_float(_pick(snapshot, "volatility_1y")),
            "max_drawdown_2y": to_float(_pick(snapshot, "max_drawdown_2y")),
            "trend_label": text_or_none(_pick(snapshot, "trend_label")),
            "market_data_reliability": text_or_none(_pick(snapshot, "market_data_reliability")),
            "financial_statement_reliability": text_or_none(
                _pick(snapshot, "financial_statement_reliability")
            ),
            "price_data_reliability_from_fetch": text_or_none(
                _pick(snapshot, "price_data_reliability_from_fetch")
            ),
            "raw_json": raw_json,
            "imported_at": imported_at,
        }

    def _chokepoint_assessment_row(
        self,
        run_id: str,
        pm_decision: dict[str, Any],
        imported_at: str,
    ) -> dict[str, Any]:
        nested = _as_dict(pm_decision.get("chokepoint_decision"))
        return {
            "assessment_id": stable_id("chokepoint", run_id),
            "run_id": run_id,
            "chokepoint_score": to_float(_pick(pm_decision, "chokepoint_score", source=nested)),
            "indispensability_score": to_float(
                _pick(pm_decision, "indispensability_score", source=nested)
            ),
            "scarcity_score": to_float(_pick(pm_decision, "scarcity_score", source=nested)),
            "customer_validation_score": to_float(
                _pick(pm_decision, "customer_validation_score", source=nested)
            ),
            "nvidia_signal_score": to_float(_pick(pm_decision, "nvidia_signal_score", source=nested)),
            "substitution_risk_score": to_float(
                _pick(pm_decision, "substitution_risk_score", source=nested)
            ),
            "timing_risk_score": to_float(_pick(pm_decision, "timing_risk_score", source=nested)),
            "market_awareness_score": to_float(
                _pick(pm_decision, "market_awareness_score", source=nested)
            ),
            "valuation_risk_score": to_float(
                _pick(pm_decision, "valuation_risk_score", source=nested)
            ),
            "serenity_thesis_quality": text_or_none(
                _pick(pm_decision, "serenity_thesis_quality", source=nested)
            ),
            "evidence_level": text_or_none(
                _pick(pm_decision, "chokepoint_evidence_level", "evidence_level", source=nested)
            ),
            "deep_research_priority": text_or_none(
                _pick(pm_decision, "deep_research_priority", source=nested)
            ),
            "scout_recommendation": text_or_none(
                _pick(pm_decision, "scout_recommendation", source=nested)
            ),
            "overlay_applied": to_int_bool(_pick(pm_decision, "chokepoint_overlay_applied")),
            "overlay_reason": text_or_none(_pick(pm_decision, "chokepoint_overlay_reason")),
            "overlay_warnings_json": dump_json(_pick(pm_decision, "chokepoint_overlay_warnings")),
            "raw_json": dump_json(nested or pm_decision),
            "imported_at": imported_at,
        }

    def _read_json(
        self,
        path: Path,
        warnings: list[ImportWarning],
        artifact_type: str,
    ) -> tuple[Any | None, str | None]:
        raw = self._read_text(path, warnings, artifact_type)
        if raw is None:
            return None, None
        try:
            return json.loads(raw), raw
        except json.JSONDecodeError as exc:
            warnings.append(
                ImportWarning(
                    "malformed_json",
                    f"{artifact_type} could not be parsed as JSON: line {exc.lineno} column {exc.colno}",
                    str(path),
                )
            )
            return None, raw

    def _read_text(
        self,
        path: Path,
        warnings: list[ImportWarning],
        artifact_type: str,
    ) -> str | None:
        try:
            return path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            try:
                return path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                warnings.append(
                    ImportWarning("file_read_error", f"{artifact_type} could not be read: {exc}", str(path))
                )
                return None
        except OSError as exc:
            warnings.append(
                ImportWarning("file_read_error", f"{artifact_type} could not be read: {exc}", str(path))
            )
            return None

    def _load_research_log(self) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
        if not self.research_log_path.exists():
            return [], {}
        rows: list[dict[str, str]] = []
        index: dict[str, dict[str, str]] = {}
        try:
            with self.research_log_path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    cleaned = {str(key): value for key, value in row.items() if key is not None}
                    rows.append(cleaned)
                    for key in self._research_log_keys(cleaned):
                        index[key] = cleaned
        except (OSError, csv.Error):
            return rows, index
        return rows, index

    def _research_log_keys(self, row: dict[str, str]) -> list[str]:
        keys: list[str] = []
        output_dir = text_or_none(row.get("output_dir"))
        if output_dir:
            for candidate in self._candidate_paths(output_dir):
                keys.append(_normalize_path(candidate))
        pm_decision_json = text_or_none(row.get("pm_decision_json"))
        if pm_decision_json:
            for candidate in self._candidate_paths(pm_decision_json):
                keys.append(_normalize_path(candidate.parent))
        return keys

    def _candidate_paths(self, value: str) -> list[Path]:
        path = Path(value)
        if path.is_absolute():
            return [path]
        return [self.outputs_dir.parent / path, self.outputs_dir / path]


def parse_evidence_context(text: str) -> list[dict[str, str]]:
    """Parse simple source blocks from evidence_context.md."""

    labels = {
        "Query Type": "query_type",
        "Expected Tier": "expected_tier",
        "Evidence Tier": "evidence_tier",
        "Source Type": "source_type",
        "Source Domain": "source_domain",
        "Title": "title",
        "URL": "url",
        "Snippet": "snippet",
    }
    items: list[dict[str, str]] = []
    current: dict[str, Any] | None = None

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        raw_lines = current.pop("_raw_lines", [])
        if current.get("url") or current.get("title") or current.get("snippet"):
            current["raw_text"] = "\n".join(raw_lines).strip()
            items.append({key: str(value) for key, value in current.items() if value is not None})
        current = None

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- Source:"):
            flush()
            current = {
                "provider": stripped.split(":", 1)[1].strip() or None,
                "_raw_lines": [line],
            }
            continue
        if current is None:
            continue
        current["_raw_lines"].append(line)
        for label, key in labels.items():
            prefix = f"{label}:"
            if stripped.startswith(prefix):
                current[key] = stripped[len(prefix) :].strip() or None
                break
    flush()
    return items


def extract_fact_records(obj: Any) -> list[dict[str, Any]]:
    if isinstance(obj, list):
        return [item for item in obj if isinstance(item, dict)]
    if isinstance(obj, dict):
        for key in ("facts", "items", "records", "cached_facts", "fresh_facts"):
            value = obj.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def group_rows_by_source_file(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["source_file"]), []).append(row)
    return grouped


def parse_run_folder(folder_name: str) -> tuple[str | None, str | None]:
    match = re.match(r"^(?P<ticker>[A-Za-z0-9.\-]+)_(?P<date>\d{8})_(?P<time>\d{6})$", folder_name)
    if not match:
        return None, None
    date_text = match.group("date")
    time_text = match.group("time")
    created_at = (
        f"{date_text[0:4]}-{date_text[4:6]}-{date_text[6:8]}"
        f"T{time_text[0:2]}:{time_text[2:4]}:{time_text[4:6]}"
    )
    return match.group("ticker").upper(), created_at


def stable_id(namespace: str, *parts: object) -> str:
    payload = "::".join("" if part is None else str(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"{namespace}_{digest}"


def sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def file_mtime_iso(path: Path) -> str | None:
    try:
        return utc_now_from_timestamp(path.stat().st_mtime)
    except OSError:
        return None


def utc_now_from_timestamp(timestamp: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec="seconds")


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return float(int(value))
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int_bool(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(bool(value))
    text = str(value).strip().lower()
    if text in {"true", "yes", "y", "1"}:
        return 1
    if text in {"false", "no", "n", "0"}:
        return 0
    return None


def _pick(primary: dict[str, Any], *keys: str, source: dict[str, Any] | None = None) -> Any:
    for key in keys:
        if key in primary and primary[key] not in (None, ""):
            return primary[key]
    if source:
        for key in keys:
            if key in source and source[key] not in (None, ""):
                return source[key]
    return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_path(path: Path | str) -> str:
    return str(Path(path).resolve(strict=False)).lower()
