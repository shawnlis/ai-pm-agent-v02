"""Export contracts for the SEC / IR evidence database."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .models import utc_now
from .repository import EvidenceRepository


LEDGER_FIELDS = [
    "company_id",
    "ticker",
    "company_name",
    "cik",
    "source_type",
    "source_name",
    "source_path",
    "source_hash",
    "source_date",
    "evidence_type",
    "evidence_id",
    "metric_or_form",
    "value",
    "unit",
    "period_end",
    "filing_date",
    "confidence",
    "fixture_only",
    "review_status",
]

METRIC_FIELDS = [
    "ticker",
    "company_name",
    "cik",
    "taxonomy",
    "concept",
    "label",
    "unit",
    "value",
    "end_date",
    "filed_date",
    "frame",
    "accession_number",
    "form",
    "fiscal_year",
    "fiscal_period",
    "source_path",
    "source_hash",
    "confidence",
    "fixture_only",
]


def export_all(repo: EvidenceRepository, out_dir: Path | str) -> dict[str, str]:
    """Write all fixture MVP export contracts and return output paths."""

    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)

    ledger_path = target / "company_evidence_ledger.csv"
    metric_path = target / "metric_history.csv"
    manifest_path = target / "source_manifest.json"
    warnings_path = target / "ingestion_warnings.md"
    report_path = target / "SEC_IR_EVIDENCE_DB_FIXTURE_MVP_REPORT.md"

    ledger_rows = _ledger_rows(repo)
    metric_rows = _metric_rows(repo)
    warnings = _warning_rows(repo)
    manifest = _source_manifest(repo, target)

    _write_csv(ledger_path, LEDGER_FIELDS, ledger_rows)
    _write_csv(metric_path, METRIC_FIELDS, metric_rows)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    warnings_path.write_text(_warnings_markdown(warnings), encoding="utf-8")
    report_path.write_text(_fixture_report(repo, ledger_rows, metric_rows, warnings, manifest), encoding="utf-8")

    return {
        "company_evidence_ledger": str(ledger_path),
        "metric_history": str(metric_path),
        "source_manifest": str(manifest_path),
        "ingestion_warnings": str(warnings_path),
        "fixture_mvp_report": str(report_path),
    }


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _ledger_rows(repo: EvidenceRepository) -> list[dict[str, Any]]:
    fact_rows = repo.fetch_all(
        """
        SELECT
            c.company_id,
            c.ticker,
            c.company_name,
            c.cik,
            sd.source_type,
            sd.source_name,
            sd.source_path,
            sd.source_hash,
            sd.source_date,
            'xbrl_fact' AS evidence_type,
            xf.fact_id AS evidence_id,
            xf.concept AS metric_or_form,
            xf.value,
            xf.unit,
            xf.end_date AS period_end,
            xf.filed_date AS filing_date,
            xf.confidence,
            xf.fixture_only,
            COALESCE(ec.review_status, 'fixture_only') AS review_status
        FROM xbrl_facts xf
        JOIN companies c ON c.company_id = xf.company_id
        JOIN source_documents sd ON sd.document_id = xf.source_document_id
        LEFT JOIN evidence_claims ec ON ec.fact_id = xf.fact_id
        ORDER BY c.ticker, xf.concept, xf.end_date
        """
    )
    filing_rows = repo.fetch_all(
        """
        SELECT
            c.company_id,
            c.ticker,
            c.company_name,
            c.cik,
            sd.source_type,
            sd.source_name,
            sd.source_path,
            sd.source_hash,
            sd.source_date,
            'sec_filing' AS evidence_type,
            sf.filing_id AS evidence_id,
            sf.form AS metric_or_form,
            '' AS value,
            '' AS unit,
            sf.report_date AS period_end,
            sf.filing_date AS filing_date,
            sf.confidence,
            sf.fixture_only,
            'fixture_only' AS review_status
        FROM sec_filings sf
        JOIN companies c ON c.company_id = sf.company_id
        JOIN source_documents sd ON sd.document_id = sf.source_document_id
        ORDER BY c.ticker, sf.filing_date DESC, sf.form
        """
    )
    return [_row_dict(row) for row in fact_rows + filing_rows]


def _metric_rows(repo: EvidenceRepository) -> list[dict[str, Any]]:
    rows = repo.fetch_all(
        """
        SELECT
            c.ticker,
            c.company_name,
            c.cik,
            xf.taxonomy,
            xf.concept,
            xf.label,
            xf.unit,
            xf.value,
            xf.end_date,
            xf.filed_date,
            xf.frame,
            xf.accession_number,
            xf.form,
            xf.fiscal_year,
            xf.fiscal_period,
            sd.source_path,
            sd.source_hash,
            xf.confidence,
            xf.fixture_only
        FROM xbrl_facts xf
        JOIN companies c ON c.company_id = xf.company_id
        JOIN source_documents sd ON sd.document_id = xf.source_document_id
        ORDER BY c.ticker, xf.concept, xf.end_date
        """
    )
    return [_row_dict(row) for row in rows]


def _warning_rows(repo: EvidenceRepository) -> list[dict[str, Any]]:
    rows = repo.fetch_all(
        """
        SELECT code, message, source_path, context_json, created_at
        FROM ingestion_warnings
        ORDER BY created_at, code, message
        """
    )
    return [_row_dict(row) for row in rows]


def _source_manifest(repo: EvidenceRepository, out_dir: Path) -> dict[str, Any]:
    source_rows = repo.fetch_all(
        """
        SELECT
            sd.source_name,
            sd.source_type,
            sd.source_path,
            sd.source_url,
            sd.source_hash,
            sd.source_date,
            sd.captured_at,
            sd.confidence,
            sd.fixture_only,
            sd.metadata_json,
            c.ticker,
            c.company_name,
            c.cik
        FROM source_documents sd
        JOIN companies c ON c.company_id = sd.company_id
        ORDER BY c.ticker, sd.source_type
        """
    )
    return {
        "generated_at": utc_now(),
        "api_level": "Level 0",
        "fixture_only": True,
        "network_access": False,
        "live_sec_api": False,
        "auth_required": False,
        "broker_access": False,
        "portfolio_access": False,
        "pm_prompt_wiring": False,
        "output_dir": str(out_dir),
        "counts": repo.summarize_counts(),
        "sources": [
            {
                "source_name": row["source_name"],
                "source_type": row["source_type"],
                "ticker": row["ticker"],
                "company_name": row["company_name"],
                "cik": row["cik"],
                "path": row["source_path"],
                "url_reference": row["source_url"],
                "hash_sha256": row["source_hash"],
                "source_date": row["source_date"],
                "captured_at": row["captured_at"],
                "confidence": row["confidence"],
                "source_level": "Level 0",
                "fixture_only": bool(row["fixture_only"]),
                "metadata": _json_loads(row["metadata_json"]),
            }
            for row in source_rows
        ],
    }


def _warnings_markdown(warnings: list[dict[str, Any]]) -> str:
    lines = [
        "# SEC / IR Evidence DB Ingestion Warnings",
        "",
        "- Source mode: fixture-only local files.",
        "- Live SEC API calls: no.",
        "- PM recommendation wiring: no.",
        "",
    ]
    if not warnings:
        lines.append("No ingestion warnings.")
        lines.append("")
        return "\n".join(lines)
    for warning in warnings:
        lines.append(f"- `{warning['code']}`: {warning['message']}")
        if warning.get("source_path"):
            lines.append(f"  - Source: `{warning['source_path']}`")
    lines.append("")
    return "\n".join(lines)


def _fixture_report(
    repo: EvidenceRepository,
    ledger_rows: list[dict[str, Any]],
    metric_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> str:
    counts = repo.summarize_counts()
    lines = [
        "# SEC / IR Evidence Database Fixture MVP Report",
        "",
        "## Boundary",
        "",
        "- This run used fixture-only local SEC-shaped JSON inputs.",
        "- No live SEC API, web search, market data, LLM, broker, IBKR, trading, portfolio, or client-data workflow was run.",
        "- The evidence DB is a source ledger and gap-monitor input, not a conclusion engine.",
        "- Outputs are not wired into PM prompts or buy/sell recommendation logic.",
        "",
        "## Output Contracts",
        "",
        "- `company_evidence_ledger.csv`",
        "- `metric_history.csv`",
        "- `source_manifest.json`",
        "- `ingestion_warnings.md`",
        "- `evidence_db.sqlite`",
        "",
        "## Counts",
        "",
    ]
    for table, count in counts.items():
        lines.append(f"- `{table}`: {count}")
    lines.extend(
        [
            "",
            "## Export Summary",
            "",
            f"- Evidence ledger rows: {len(ledger_rows)}",
            f"- Metric history rows: {len(metric_rows)}",
            f"- Warning rows: {len(warnings)}",
            f"- Manifest fixture_only: `{manifest['fixture_only']}`",
            f"- Manifest API level: `{manifest['api_level']}`",
            "",
        ]
    )
    return "\n".join(lines)


def _row_dict(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _json_loads(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
