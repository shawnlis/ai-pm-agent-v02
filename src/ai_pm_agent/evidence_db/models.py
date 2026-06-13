"""Data models for the fixture-first SEC / IR evidence database."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stable_id(prefix: str, *parts: object) -> str:
    material = "|".join("" if part is None else str(part) for part in parts)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


@dataclass(frozen=True)
class CompanyRef:
    company_id: str
    ticker: str
    company_name: str
    cik: str
    cik_padded: str
    exchange: str = ""
    source_level: str = "Level 0"
    created_at: str = ""


@dataclass(frozen=True)
class SourceDocument:
    document_id: str
    company_id: str
    source_type: str
    source_name: str
    source_path: str
    source_url: str
    source_hash: str
    source_date: str
    captured_at: str
    confidence: str
    fixture_only: bool
    metadata_json: str = "{}"


@dataclass(frozen=True)
class SecFiling:
    filing_id: str
    company_id: str
    source_document_id: str
    accession_number: str
    form: str
    filing_date: str
    report_date: str
    primary_document: str
    source_url: str
    confidence: str
    fixture_only: bool


@dataclass(frozen=True)
class XbrlFact:
    fact_id: str
    company_id: str
    source_document_id: str
    taxonomy: str
    concept: str
    label: str
    unit: str
    value: float
    end_date: str
    filed_date: str
    frame: str
    accession_number: str
    form: str
    fiscal_year: int | None
    fiscal_period: str
    confidence: str
    fixture_only: bool


@dataclass(frozen=True)
class EvidenceClaim:
    claim_id: str
    company_id: str
    source_document_id: str
    fact_id: str
    claim_type: str
    claim_text: str
    source_date: str
    confidence: str
    review_status: str
    fixture_only: bool


@dataclass(frozen=True)
class IngestionRun:
    run_id: str
    ticker: str
    company_name: str
    started_at: str
    completed_at: str
    source_mode: str
    fixture_only: bool
    status: str
    warnings_count: int
    errors_count: int
    output_dir: str


@dataclass(frozen=True)
class IngestionWarning:
    warning_id: str
    run_id: str
    code: str
    message: str
    source_path: str
    context_json: str
    created_at: str
