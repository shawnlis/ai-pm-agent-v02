"""Fixture-first SEC / IR evidence database package."""

from .models import (
    CompanyRef,
    EvidenceClaim,
    IngestionRun,
    IngestionWarning,
    SecFiling,
    SourceDocument,
    XbrlFact,
)
from .repository import DEFAULT_DB_PATH, EvidenceRepository
from .sec_edgar import fetch_sec_companyfacts, fetch_sec_submissions, resolve_cik_from_ticker

__all__ = [
    "CompanyRef",
    "DEFAULT_DB_PATH",
    "EvidenceClaim",
    "EvidenceRepository",
    "fetch_sec_companyfacts",
    "fetch_sec_submissions",
    "IngestionRun",
    "IngestionWarning",
    "resolve_cik_from_ticker",
    "SecFiling",
    "SourceDocument",
    "XbrlFact",
]
