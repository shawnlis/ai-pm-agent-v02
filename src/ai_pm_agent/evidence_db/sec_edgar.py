"""SEC EDGAR parsers and explicit Level 1 public API adapter."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

from . import cache as sec_cache
from . import http_client
from .cache import CachedSecJson, DEFAULT_SEC_CACHE_DIR
from .exports import export_all
from .http_client import SecHttpError
from .models import (
    CompanyRef,
    EvidenceClaim,
    IngestionRun,
    IngestionWarning,
    SecFiling,
    SourceDocument,
    XbrlFact,
    stable_id,
    utc_now,
)
from .repository import DEFAULT_DB_PATH, EvidenceRepository
from .warnings import (
    MISSING_CIK,
    MISSING_FACT_VALUE,
    MISSING_FILING_DATE,
    SEC_CACHE_HIT,
    SEC_CACHE_MISS,
    SEC_CIK_RESOLUTION_FAILED,
    SEC_COMPANYFACTS_NOT_FOUND,
    SEC_FETCH_FAIL_CLOSED,
    SEC_INVALID_RESPONSE,
    SEC_LIVE_FETCH_USED,
    SEC_OFFLINE_MODE_NETWORK_BLOCKED,
    SEC_SUBMISSIONS_NOT_FOUND,
    SEC_USER_AGENT_REQUIRED,
    SOURCE_FIXTURE_ONLY,
    UNKNOWN_COMPANY,
    UNSUPPORTED_FACT_UNIT,
    make_warning,
    with_run_id,
)


SEC_EDGAR_FIXTURE_ONLY = True
LIVE_HTTP_ENABLED = True
SUPPORTED_FACT_UNITS = {"USD", "shares", "pure", "USD/shares"}
DEFAULT_OUTPUT_DIR = Path("reports") / "sec_ir_evidence_db" / "fixture_mvp"
SEC_TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik_padded}.json"
SEC_COMPANYFACTS_URL_TEMPLATE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"


@dataclass(frozen=True)
class ParsedSubmissions:
    company: CompanyRef
    source_document: SourceDocument
    filings: list[SecFiling]
    warnings: list[IngestionWarning]


@dataclass(frozen=True)
class ParsedCompanyFacts:
    company: CompanyRef
    source_document: SourceDocument
    facts: list[XbrlFact]
    warnings: list[IngestionWarning]


class SecEdgarLiveFetchError(RuntimeError):
    """Fail-closed live SEC adapter error with a structured warning code."""

    def __init__(self, code: str, message: str, *, url: str = "", status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.url = url
        self.status_code = status_code


def load_json_fixture(path: Path | str) -> dict[str, Any]:
    fixture_path = Path(path)
    with fixture_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"SEC fixture must contain a JSON object: {fixture_path}")
    return payload


def parse_submissions_fixture(path_or_payload: Path | str | dict[str, Any], *, ticker: str, company_name: str) -> ParsedSubmissions:
    payload, source_path, source_hash = _payload_and_source(path_or_payload)
    company = _company_from_payload(payload, ticker=ticker, company_name=company_name)
    warnings: list[IngestionWarning] = [
        make_warning(
            SOURCE_FIXTURE_ONLY,
            "SEC submissions source is a local fixture; live EDGAR access is disabled for this MVP.",
            source_path=source_path,
            context={"source_type": "submissions"},
        )
    ]
    if not company.cik:
        warnings.append(
            make_warning(
                MISSING_CIK,
                f"Missing CIK for ticker {ticker.upper()} in submissions fixture.",
                source_path=source_path,
            )
        )
    if not company.company_name or company.company_name.upper() == "UNKNOWN":
        warnings.append(
            make_warning(
                UNKNOWN_COMPANY,
                f"Missing company name for ticker {ticker.upper()} in submissions fixture.",
                source_path=source_path,
            )
        )

    recent = _safe_dict(_safe_dict(payload.get("filings")).get("recent"))
    row_count = _recent_row_count(recent)
    source_document = _source_document(
        company=company,
        source_type="sec_submissions_fixture",
        source_name=f"{company.ticker} SEC submissions fixture",
        source_path=source_path,
        source_hash=source_hash,
        source_date=_max_recent_date(recent, "filingDate"),
        metadata={"fixture_only": True, "endpoint_shape": "submissions"},
    )
    filings: list[SecFiling] = []
    for index in range(row_count):
        accession_number = _recent_value(recent, "accessionNumber", index)
        form = _recent_value(recent, "form", index)
        filing_date = _recent_value(recent, "filingDate", index)
        report_date = _recent_value(recent, "reportDate", index)
        primary_document = _recent_value(recent, "primaryDocument", index)
        if not filing_date:
            warnings.append(
                make_warning(
                    MISSING_FILING_DATE,
                    f"Missing filing date for submissions row {index}.",
                    source_path=source_path,
                    context={"row_index": index, "accession_number": accession_number},
                )
            )
        if not accession_number and not form and not filing_date:
            continue
        filings.append(
            SecFiling(
                filing_id=stable_id("filing", company.company_id, accession_number, form, filing_date, index),
                company_id=company.company_id,
                source_document_id=source_document.document_id,
                accession_number=accession_number,
                form=form,
                filing_date=filing_date,
                report_date=report_date,
                primary_document=primary_document,
                source_url=_sec_archive_url(company.cik, accession_number, primary_document),
                confidence="high_fixture_official_shape",
                fixture_only=True,
            )
        )
    return ParsedSubmissions(company=company, source_document=source_document, filings=filings, warnings=warnings)


def parse_companyfacts_fixture(path_or_payload: Path | str | dict[str, Any], *, ticker: str, company_name: str) -> ParsedCompanyFacts:
    payload, source_path, source_hash = _payload_and_source(path_or_payload)
    company = _company_from_payload(payload, ticker=ticker, company_name=company_name)
    warnings: list[IngestionWarning] = [
        make_warning(
            SOURCE_FIXTURE_ONLY,
            "SEC companyfacts source is a local fixture; live EDGAR access is disabled for this MVP.",
            source_path=source_path,
            context={"source_type": "companyfacts"},
        )
    ]
    if not company.cik:
        warnings.append(
            make_warning(
                MISSING_CIK,
                f"Missing CIK for ticker {ticker.upper()} in companyfacts fixture.",
                source_path=source_path,
            )
        )

    source_document = _source_document(
        company=company,
        source_type="sec_companyfacts_fixture",
        source_name=f"{company.ticker} SEC companyfacts fixture",
        source_path=source_path,
        source_hash=source_hash,
        source_date=_max_companyfacts_date(payload),
        metadata={"fixture_only": True, "endpoint_shape": "companyfacts"},
    )
    facts: list[XbrlFact] = []
    facts_payload = _safe_dict(payload.get("facts"))
    for taxonomy, taxonomy_payload in facts_payload.items():
        concepts = _safe_dict(taxonomy_payload)
        for concept, concept_payload in concepts.items():
            concept_dict = _safe_dict(concept_payload)
            label = str(concept_dict.get("label") or concept)
            units = _safe_dict(concept_dict.get("units"))
            for unit, unit_facts in units.items():
                if unit not in SUPPORTED_FACT_UNITS:
                    warnings.append(
                        make_warning(
                            UNSUPPORTED_FACT_UNIT,
                            f"Unsupported XBRL fact unit `{unit}` for {taxonomy}:{concept}.",
                            source_path=source_path,
                            context={"taxonomy": taxonomy, "concept": concept, "unit": unit},
                        )
                    )
                    continue
                if not isinstance(unit_facts, list):
                    continue
                for index, fact_payload in enumerate(unit_facts):
                    fact_dict = _safe_dict(fact_payload)
                    raw_value = fact_dict.get("val")
                    if raw_value is None:
                        warnings.append(
                            make_warning(
                                MISSING_FACT_VALUE,
                                f"Missing XBRL fact value for {taxonomy}:{concept} row {index}.",
                                source_path=source_path,
                                context={"taxonomy": taxonomy, "concept": concept, "unit": unit, "row_index": index},
                            )
                        )
                        continue
                    numeric_value = _numeric_value(raw_value)
                    if numeric_value is None:
                        warnings.append(
                            make_warning(
                                MISSING_FACT_VALUE,
                                f"Non-numeric XBRL fact value for {taxonomy}:{concept} row {index}.",
                                source_path=source_path,
                                context={"taxonomy": taxonomy, "concept": concept, "unit": unit, "row_index": index},
                            )
                        )
                        continue
                    facts.append(
                        XbrlFact(
                            fact_id=stable_id(
                                "fact",
                                company.company_id,
                                taxonomy,
                                concept,
                                unit,
                                fact_dict.get("end", ""),
                                fact_dict.get("filed", ""),
                                fact_dict.get("accn", ""),
                                numeric_value,
                            ),
                            company_id=company.company_id,
                            source_document_id=source_document.document_id,
                            taxonomy=taxonomy,
                            concept=concept,
                            label=label,
                            unit=unit,
                            value=numeric_value,
                            end_date=str(fact_dict.get("end") or ""),
                            filed_date=str(fact_dict.get("filed") or ""),
                            frame=str(fact_dict.get("frame") or ""),
                            accession_number=str(fact_dict.get("accn") or ""),
                            form=str(fact_dict.get("form") or ""),
                            fiscal_year=_optional_int(fact_dict.get("fy")),
                            fiscal_period=str(fact_dict.get("fp") or ""),
                            confidence="high_fixture_official_shape",
                            fixture_only=True,
                        )
                    )
    return ParsedCompanyFacts(company=company, source_document=source_document, facts=facts, warnings=warnings)


def build_evidence_claims(facts: list[XbrlFact], company: CompanyRef) -> list[EvidenceClaim]:
    claims: list[EvidenceClaim] = []
    for fact in facts:
        claim_text = (
            f"{company.ticker} reported {fact.concept} of {fact.value:g} {fact.unit} "
            f"for period ending {fact.end_date or 'UNKNOWN'}."
        )
        claims.append(
            EvidenceClaim(
                claim_id=stable_id("claim", fact.fact_id, claim_text),
                company_id=company.company_id,
                source_document_id=fact.source_document_id,
                fact_id=fact.fact_id,
                claim_type="xbrl_metric",
                claim_text=claim_text,
                source_date=fact.filed_date,
                confidence=fact.confidence,
                review_status="fixture_only_review_required",
                fixture_only=True,
            )
        )
    return claims


def resolve_cik_from_ticker(
    ticker: str,
    cache_dir: Path | str,
    user_agent: str,
    force_refresh: bool = False,
) -> str:
    """Resolve a ticker to an unpadded SEC CIK using the public ticker JSON."""

    cik, _ = _resolve_cik_from_ticker_with_result(
        ticker=ticker,
        cache_dir=cache_dir,
        user_agent=user_agent,
        force_refresh=force_refresh,
    )
    return cik


def fetch_sec_submissions(
    cik_or_ticker: str,
    user_agent: str,
    cache_dir: Path | str,
    force_refresh: bool = False,
) -> CachedSecJson:
    """Fetch or read cached public SEC submissions JSON."""

    cik = cik_or_ticker.strip()
    if not cik.isdigit():
        cik = resolve_cik_from_ticker(cik, cache_dir, user_agent, force_refresh=force_refresh)
    cik_padded = _pad_cik(cik)
    if not cik_padded:
        raise SecEdgarLiveFetchError(SEC_SUBMISSIONS_NOT_FOUND, f"Cannot fetch submissions without a valid CIK: {cik_or_ticker}")
    return _fetch_or_cache_sec_json(
        url=SEC_SUBMISSIONS_URL_TEMPLATE.format(cik_padded=cik_padded),
        cache_name=f"submissions_{cik_padded}.json",
        cache_dir=cache_dir,
        user_agent=user_agent,
        force_refresh=force_refresh,
    )


def fetch_sec_companyfacts(
    cik: str,
    user_agent: str,
    cache_dir: Path | str,
    force_refresh: bool = False,
) -> CachedSecJson:
    """Fetch or read cached public SEC companyfacts JSON."""

    cik_padded = _pad_cik(cik)
    if not cik_padded:
        raise SecEdgarLiveFetchError(SEC_COMPANYFACTS_NOT_FOUND, f"Cannot fetch companyfacts without a valid CIK: {cik}")
    return _fetch_or_cache_sec_json(
        url=SEC_COMPANYFACTS_URL_TEMPLATE.format(cik_padded=cik_padded),
        cache_name=f"companyfacts_{cik_padded}.json",
        cache_dir=cache_dir,
        user_agent=user_agent,
        force_refresh=force_refresh,
    )


def import_live_sec(
    *,
    ticker: str,
    company_name: str,
    user_agent: str,
    out_dir: Path | str = DEFAULT_OUTPUT_DIR,
    db_path: Path | str | None = None,
    cik: str | None = None,
    cache_dir: Path | str = DEFAULT_SEC_CACHE_DIR,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Import public SEC EDGAR data in explicit Level 1 live mode."""

    target = Path(out_dir)
    database_path = Path(db_path) if db_path is not None else target / DEFAULT_DB_PATH.name
    started_at = utc_now()
    run_id = stable_id("ingestion_run", ticker.upper(), company_name, "live", started_at)
    warnings: list[IngestionWarning] = [
        make_warning(
            SEC_LIVE_FETCH_USED,
            "Explicit --live-sec-fetch mode was used for public SEC EDGAR data.",
            context={"api_level": "Level 1", "network_access": True, "live_sec_api": True},
        )
    ]
    company = CompanyRef(
        company_id=stable_id("company", ticker.upper(), cik or "", company_name),
        ticker=ticker.strip().upper(),
        company_name=company_name,
        cik=str(cik or ""),
        cik_padded=_pad_cik(str(cik or "")),
        source_level="Level 1",
        created_at=utc_now(),
    )
    source_documents: list[SourceDocument] = []
    filings: list[SecFiling] = []
    facts: list[XbrlFact] = []
    claims: list[EvidenceClaim] = []
    status = "completed"
    errors_count = 0

    try:
        _require_user_agent(user_agent)
        resolved_cik = str(cik).strip() if cik else ""
        if not resolved_cik:
            resolved_cik, ticker_result = _resolve_cik_from_ticker_with_result(
                ticker=ticker,
                cache_dir=cache_dir,
                user_agent=user_agent,
                force_refresh=force_refresh,
            )
            warnings.append(_cache_warning(ticker_result, "company_tickers"))

        submissions_result = fetch_sec_submissions(resolved_cik, user_agent, cache_dir, force_refresh=force_refresh)
        companyfacts_result = fetch_sec_companyfacts(resolved_cik, user_agent, cache_dir, force_refresh=force_refresh)
        warnings.append(_cache_warning(submissions_result, "submissions"))
        warnings.append(_cache_warning(companyfacts_result, "companyfacts"))

        parsed_submissions = parse_submissions_fixture(submissions_result.payload, ticker=ticker, company_name=company_name)
        parsed_companyfacts = parse_companyfacts_fixture(companyfacts_result.payload, ticker=ticker, company_name=company_name)
        warnings.extend(_live_parse_warnings(parsed_submissions.warnings, submissions_result.cache_path))
        warnings.extend(_live_parse_warnings(parsed_companyfacts.warnings, companyfacts_result.cache_path))

        company = _company_as_level_one(_merge_company(parsed_submissions.company, parsed_companyfacts.company), resolved_cik)
        submissions_source = _live_source_document(
            company=company,
            result=submissions_result,
            endpoint_shape="submissions",
            source_date=_max_recent_date(_safe_dict(_safe_dict(submissions_result.payload.get("filings")).get("recent")), "filingDate"),
        )
        companyfacts_source = _live_source_document(
            company=company,
            result=companyfacts_result,
            endpoint_shape="companyfacts",
            source_date=_max_companyfacts_date(companyfacts_result.payload),
        )
        source_documents = [submissions_source, companyfacts_source]
        filings = [
            _replace_filing_source(filing, company.company_id, submissions_source.document_id, fixture_only=False)
            for filing in parsed_submissions.filings
        ]
        facts = [
            _replace_fact_source(fact, company.company_id, companyfacts_source.document_id, fixture_only=False)
            for fact in parsed_companyfacts.facts
        ]
        claims = [
            _replace_claim_company_id(claim, company.company_id)
            for claim in build_evidence_claims(facts, company)
        ]
    except (SecHttpError, SecEdgarLiveFetchError, json.JSONDecodeError) as exc:
        status = "failed"
        errors_count = 1
        warning_code = getattr(exc, "code", SEC_INVALID_RESPONSE)
        warnings.append(
            make_warning(
                warning_code,
                str(exc),
                context={
                    "url": getattr(exc, "url", ""),
                    "status_code": getattr(exc, "status_code", None),
                },
            )
        )
        warnings.append(
            make_warning(
                SEC_FETCH_FAIL_CLOSED,
                "SEC live fetch failed closed; no evidence was fabricated.",
                context={"ticker": ticker.upper(), "company_name": company_name},
            )
        )

    run_warnings = [with_run_id(warning, run_id) for warning in warnings]
    run = IngestionRun(
        run_id=run_id,
        ticker=company.ticker,
        company_name=company.company_name,
        started_at=started_at,
        completed_at=utc_now(),
        source_mode="sec_edgar_level1_live",
        fixture_only=False,
        status=status,
        warnings_count=len(run_warnings),
        errors_count=errors_count,
        output_dir=str(target),
    )

    with EvidenceRepository(database_path) as repo:
        repo.insert_ingestion_run(run)
        repo.insert_company(company)
        for source_document in source_documents:
            repo.insert_source_document(source_document)
        for filing in filings:
            repo.insert_sec_filing(filing)
        for fact in facts:
            repo.insert_xbrl_fact(fact)
        for claim in claims:
            repo.insert_evidence_claim(claim)
        for warning in run_warnings:
            repo.insert_ingestion_warning(warning)
        repo.commit()
        outputs = export_all(
            repo,
            target,
            manifest_context={
                "api_level": "Level 1",
                "fixture_only": False,
                "network_access": status == "completed",
                "live_sec_api": True,
                "source_type": "SEC_EDGAR_PUBLIC_API",
            },
            report_filename="SEC_IR_EVIDENCE_DB_LIVE_FETCH_REPORT.md",
        )

    outputs["database"] = str(database_path)
    outputs["run_id"] = run_id
    outputs["status"] = status
    outputs["warnings_count"] = len(run_warnings)
    outputs["facts_count"] = len(facts)
    outputs["filings_count"] = len(filings)
    outputs["live_sec_api"] = True
    return outputs


def import_fixtures(
    *,
    submissions_fixture: Path | str,
    companyfacts_fixture: Path | str,
    ticker: str,
    company_name: str,
    out_dir: Path | str = DEFAULT_OUTPUT_DIR,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    target = Path(out_dir)
    database_path = Path(db_path) if db_path is not None else target / DEFAULT_DB_PATH.name
    started_at = utc_now()
    run_id = stable_id("ingestion_run", ticker.upper(), company_name, started_at)
    submissions = parse_submissions_fixture(submissions_fixture, ticker=ticker, company_name=company_name)
    companyfacts = parse_companyfacts_fixture(companyfacts_fixture, ticker=ticker, company_name=company_name)
    company = _merge_company(submissions.company, companyfacts.company)
    filings = [_replace_filing_company_id(filing, company.company_id) for filing in submissions.filings]
    facts = [_replace_fact_company_id(fact, company.company_id) for fact in companyfacts.facts]
    claims = [_replace_claim_company_id(claim, company.company_id) for claim in build_evidence_claims(facts, company)]
    warnings = [with_run_id(warning, run_id) for warning in submissions.warnings + companyfacts.warnings]
    run = IngestionRun(
        run_id=run_id,
        ticker=company.ticker,
        company_name=company.company_name,
        started_at=started_at,
        completed_at=utc_now(),
        source_mode="fixture_only",
        fixture_only=True,
        status="completed",
        warnings_count=len(warnings),
        errors_count=0,
        output_dir=str(target),
    )

    with EvidenceRepository(database_path) as repo:
        repo.insert_ingestion_run(run)
        repo.insert_company(company)
        repo.insert_source_document(_replace_company_id(submissions.source_document, company.company_id))
        repo.insert_source_document(_replace_company_id(companyfacts.source_document, company.company_id))
        for filing in filings:
            repo.insert_sec_filing(filing)
        for fact in facts:
            repo.insert_xbrl_fact(fact)
        for claim in claims:
            repo.insert_evidence_claim(claim)
        for warning in warnings:
            repo.insert_ingestion_warning(warning)
        repo.commit()
        outputs = export_all(repo, target)

    outputs["database"] = str(database_path)
    outputs["run_id"] = run_id
    outputs["warnings_count"] = len(warnings)
    outputs["facts_count"] = len(facts)
    outputs["filings_count"] = len(filings)
    return outputs


def dry_run_fixtures(
    *,
    submissions_fixture: Path | str,
    companyfacts_fixture: Path | str,
    ticker: str,
    company_name: str,
) -> dict[str, Any]:
    submissions = parse_submissions_fixture(submissions_fixture, ticker=ticker, company_name=company_name)
    companyfacts = parse_companyfacts_fixture(companyfacts_fixture, ticker=ticker, company_name=company_name)
    return {
        "dry_run": True,
        "fixture_only": True,
        "live_sec_api": False,
        "ticker": ticker.upper(),
        "company_name": company_name,
        "filings_count": len(submissions.filings),
        "facts_count": len(companyfacts.facts),
        "warnings_count": len(submissions.warnings) + len(companyfacts.warnings),
    }


def export_existing_database(*, db_path: Path | str, out_dir: Path | str) -> dict[str, str]:
    with EvidenceRepository(db_path, read_only=True) as repo:
        return export_all(repo, out_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import SEC / IR evidence fixtures or explicit SEC EDGAR Level 1 live data.")
    parser.add_argument("--submissions-fixture", type=Path)
    parser.add_argument("--companyfacts-fixture", type=Path)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--company-name", required=True)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--export-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--live-sec-fetch", action="store_true")
    parser.add_argument("--cik")
    parser.add_argument("--sec-user-agent")
    parser.add_argument("--sec-cache-dir", type=Path, default=DEFAULT_SEC_CACHE_DIR)
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)

    db_path = args.db or args.out_dir / DEFAULT_DB_PATH.name
    if args.export_only:
        outputs = export_existing_database(db_path=db_path, out_dir=args.out_dir)
        print(json.dumps({"export_only": True, "outputs": outputs}, indent=2, sort_keys=True))
        return 0

    fixture_inputs_present = args.submissions_fixture is not None or args.companyfacts_fixture is not None
    if args.offline and args.live_sec_fetch:
        parser.error("--offline blocks --live-sec-fetch; use fixture inputs or cached export-only mode.")
    if args.live_sec_fetch and fixture_inputs_present:
        parser.error("--live-sec-fetch cannot be combined with fixture inputs; choose fixture-only or live mode.")
    if args.live_sec_fetch and not (args.sec_user_agent or "").strip():
        parser.error("--live-sec-fetch requires --sec-user-agent.")
    if not args.live_sec_fetch and not fixture_inputs_present:
        parser.error("fixture mode is the default; provide both fixtures or pass --live-sec-fetch explicitly.")
    if not args.live_sec_fetch and (args.submissions_fixture is None or args.companyfacts_fixture is None):
        parser.error("--submissions-fixture and --companyfacts-fixture are both required in fixture mode.")

    if args.dry_run:
        if args.live_sec_fetch:
            summary = {
                "dry_run": True,
                "fixture_only": False,
                "live_sec_api": True,
                "network_access": False,
                "ticker": args.ticker.upper(),
                "company_name": args.company_name,
                "message": "Live SEC fetch dry run did not perform network access.",
            }
        else:
            summary = dry_run_fixtures(
                submissions_fixture=args.submissions_fixture,
                companyfacts_fixture=args.companyfacts_fixture,
                ticker=args.ticker,
                company_name=args.company_name,
            )
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    if args.live_sec_fetch:
        outputs = import_live_sec(
            ticker=args.ticker,
            company_name=args.company_name,
            user_agent=args.sec_user_agent or "",
            out_dir=args.out_dir,
            db_path=db_path,
            cik=args.cik,
            cache_dir=args.sec_cache_dir,
            force_refresh=args.force_refresh,
        )
        if outputs.get("status") != "completed":
            print(json.dumps(outputs, indent=2, sort_keys=True), file=sys.stderr)
            return 2
    else:
        outputs = import_fixtures(
            submissions_fixture=args.submissions_fixture,
            companyfacts_fixture=args.companyfacts_fixture,
            ticker=args.ticker,
            company_name=args.company_name,
            out_dir=args.out_dir,
            db_path=db_path,
        )
    if args.verbose:
        print(json.dumps(outputs, indent=2, sort_keys=True))
    else:
        print(f"wrote SEC / IR evidence fixture MVP outputs to {args.out_dir}")
    return 0


def _payload_and_source(path_or_payload: Path | str | dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    if isinstance(path_or_payload, dict):
        payload = path_or_payload
        source_text = "<dict_fixture>"
        source_hash = _hash_text(json.dumps(payload, sort_keys=True))
    else:
        path = Path(path_or_payload)
        payload = load_json_fixture(path)
        source_text = str(path)
        source_hash = _hash_file(path)
    return payload, source_text, source_hash


def _require_user_agent(user_agent: str) -> None:
    if not (user_agent or "").strip():
        raise SecHttpError(SEC_USER_AGENT_REQUIRED, "SEC EDGAR live fetch requires --sec-user-agent.")


def _fetch_or_cache_sec_json(
    *,
    url: str,
    cache_name: str,
    cache_dir: Path | str,
    user_agent: str,
    force_refresh: bool,
) -> CachedSecJson:
    _require_user_agent(user_agent)
    if not force_refresh:
        try:
            cached = sec_cache.read_cached_json(cache_dir, cache_name, url=url)
        except json.JSONDecodeError as exc:
            raise SecHttpError(SEC_INVALID_RESPONSE, f"Cached SEC JSON is invalid: {cache_name}", url=url) from exc
        if cached is not None:
            if not isinstance(cached.payload, dict):
                raise SecHttpError(SEC_INVALID_RESPONSE, f"Cached SEC JSON is not an object: {cache_name}", url=url)
            return cached
    response = http_client.fetch_json(url, user_agent)
    if not isinstance(response.payload, dict):
        raise SecHttpError(SEC_INVALID_RESPONSE, f"SEC JSON response is not an object: {url}", url=url, status_code=response.status_code)
    return sec_cache.write_cached_json(cache_dir, cache_name, response, user_agent=user_agent)


def _resolve_cik_from_ticker_with_result(
    *,
    ticker: str,
    cache_dir: Path | str,
    user_agent: str,
    force_refresh: bool,
) -> tuple[str, CachedSecJson]:
    ticker_norm = ticker.strip().upper()
    result = _fetch_or_cache_sec_json(
        url=SEC_TICKER_URL,
        cache_name="company_tickers.json",
        cache_dir=cache_dir,
        user_agent=user_agent,
        force_refresh=force_refresh,
    )
    records = result.payload.values() if isinstance(result.payload, dict) else []
    for row in records:
        if not isinstance(row, dict):
            continue
        if str(row.get("ticker") or "").strip().upper() == ticker_norm:
            cik = str(row.get("cik_str") or "").strip()
            if cik:
                return cik, result
    raise SecEdgarLiveFetchError(
        SEC_CIK_RESOLUTION_FAILED,
        f"Could not resolve SEC CIK for ticker {ticker_norm}.",
        url=SEC_TICKER_URL,
    )


def _cache_warning(result: CachedSecJson, source_name: str) -> IngestionWarning:
    code = SEC_CACHE_HIT if result.cache_hit else SEC_CACHE_MISS
    action = "hit" if result.cache_hit else "miss"
    return make_warning(
        code,
        f"SEC cache {action} for {source_name}.",
        source_path=result.cache_path,
        context={
            "source_url": result.url,
            "cache_path": str(result.cache_path),
            "retrieved_at": result.retrieved_at,
            "sha256": result.sha256,
            "api_level": result.api_level,
        },
    )


def _live_parse_warnings(warnings: list[IngestionWarning], source_path: Path) -> list[IngestionWarning]:
    live_warnings: list[IngestionWarning] = []
    for warning in warnings:
        if warning.code == SOURCE_FIXTURE_ONLY:
            continue
        live_warnings.append(
            IngestionWarning(
                warning_id=stable_id(
                    "warning",
                    "live",
                    warning.code,
                    warning.message,
                    str(source_path),
                    warning.context_json,
                ),
                run_id=warning.run_id,
                code=warning.code,
                message=warning.message,
                source_path=str(source_path),
                context_json=warning.context_json,
                created_at=warning.created_at,
            )
        )
    return live_warnings


def _live_source_document(
    *,
    company: CompanyRef,
    result: CachedSecJson,
    endpoint_shape: str,
    source_date: str,
) -> SourceDocument:
    metadata = {
        "api_level": "Level 1",
        "source_type": "SEC_EDGAR_PUBLIC_API",
        "endpoint_shape": endpoint_shape,
        "network_access": True,
        "live_sec_api": True,
        "cache_path": str(result.cache_path),
        "cache_metadata_path": str(result.metadata_path),
        "cache_hit": result.cache_hit,
        "retrieved_at": result.retrieved_at,
        "source_url": result.url,
        "sha256": result.sha256,
    }
    return SourceDocument(
        document_id=stable_id("source", company.company_id, "SEC_EDGAR_PUBLIC_API", endpoint_shape, result.sha256, result.url),
        company_id=company.company_id,
        source_type="SEC_EDGAR_PUBLIC_API",
        source_name=f"{company.ticker} SEC EDGAR {endpoint_shape}",
        source_path=str(result.cache_path),
        source_url=result.url,
        source_hash=result.sha256,
        source_date=source_date,
        captured_at=result.retrieved_at,
        confidence="high_official_sec_edgar_public_api",
        fixture_only=False,
        metadata_json=json.dumps(metadata, sort_keys=True),
    )


def _company_as_level_one(company: CompanyRef, cik: str) -> CompanyRef:
    resolved_cik = str(cik or company.cik or "").strip()
    return CompanyRef(
        company_id=stable_id("company", company.ticker, resolved_cik, company.company_name),
        ticker=company.ticker,
        company_name=company.company_name,
        cik=resolved_cik,
        cik_padded=_pad_cik(resolved_cik),
        exchange=company.exchange,
        source_level="Level 1",
        created_at=company.created_at or utc_now(),
    )


def _company_from_payload(payload: dict[str, Any], *, ticker: str, company_name: str) -> CompanyRef:
    ticker_norm = ticker.strip().upper()
    cik = str(payload.get("cik") or payload.get("cikNumber") or "").strip()
    if cik.endswith(".0"):
        cik = cik[:-2]
    resolved_name = str(payload.get("name") or payload.get("entityName") or company_name or "UNKNOWN").strip()
    tickers = payload.get("tickers")
    exchanges = payload.get("exchanges")
    exchange = ""
    if isinstance(tickers, list) and isinstance(exchanges, list):
        for index, candidate in enumerate(tickers):
            if str(candidate).upper() == ticker_norm and index < len(exchanges):
                exchange = str(exchanges[index] or "")
                break
    return CompanyRef(
        company_id=stable_id("company", ticker_norm, cik, resolved_name),
        ticker=ticker_norm,
        company_name=resolved_name,
        cik=cik,
        cik_padded=_pad_cik(cik),
        exchange=exchange,
        source_level="Level 0",
        created_at=utc_now(),
    )


def _source_document(
    *,
    company: CompanyRef,
    source_type: str,
    source_name: str,
    source_path: str,
    source_hash: str,
    source_date: str,
    metadata: dict[str, Any],
) -> SourceDocument:
    return SourceDocument(
        document_id=stable_id("source", company.company_id, source_type, source_hash, source_path),
        company_id=company.company_id,
        source_type=source_type,
        source_name=source_name,
        source_path=source_path,
        source_url=_sec_endpoint_reference(company.cik, source_type),
        source_hash=source_hash,
        source_date=source_date,
        captured_at=utc_now(),
        confidence="high_fixture_official_shape",
        fixture_only=True,
        metadata_json=json.dumps(metadata, sort_keys=True),
    )


def _replace_company_id(source_document: SourceDocument, company_id: str) -> SourceDocument:
    return SourceDocument(
        document_id=source_document.document_id,
        company_id=company_id,
        source_type=source_document.source_type,
        source_name=source_document.source_name,
        source_path=source_document.source_path,
        source_url=source_document.source_url,
        source_hash=source_document.source_hash,
        source_date=source_document.source_date,
        captured_at=source_document.captured_at,
        confidence=source_document.confidence,
        fixture_only=source_document.fixture_only,
        metadata_json=source_document.metadata_json,
    )


def _replace_filing_company_id(filing: SecFiling, company_id: str) -> SecFiling:
    return SecFiling(
        filing_id=filing.filing_id,
        company_id=company_id,
        source_document_id=filing.source_document_id,
        accession_number=filing.accession_number,
        form=filing.form,
        filing_date=filing.filing_date,
        report_date=filing.report_date,
        primary_document=filing.primary_document,
        source_url=filing.source_url,
        confidence=filing.confidence,
        fixture_only=filing.fixture_only,
    )


def _replace_filing_source(
    filing: SecFiling,
    company_id: str,
    source_document_id: str,
    *,
    fixture_only: bool,
) -> SecFiling:
    return SecFiling(
        filing_id=filing.filing_id,
        company_id=company_id,
        source_document_id=source_document_id,
        accession_number=filing.accession_number,
        form=filing.form,
        filing_date=filing.filing_date,
        report_date=filing.report_date,
        primary_document=filing.primary_document,
        source_url=filing.source_url,
        confidence="high_official_sec_edgar_public_api",
        fixture_only=fixture_only,
    )


def _replace_fact_company_id(fact: XbrlFact, company_id: str) -> XbrlFact:
    return XbrlFact(
        fact_id=fact.fact_id,
        company_id=company_id,
        source_document_id=fact.source_document_id,
        taxonomy=fact.taxonomy,
        concept=fact.concept,
        label=fact.label,
        unit=fact.unit,
        value=fact.value,
        end_date=fact.end_date,
        filed_date=fact.filed_date,
        frame=fact.frame,
        accession_number=fact.accession_number,
        form=fact.form,
        fiscal_year=fact.fiscal_year,
        fiscal_period=fact.fiscal_period,
        confidence=fact.confidence,
        fixture_only=fact.fixture_only,
    )


def _replace_fact_source(
    fact: XbrlFact,
    company_id: str,
    source_document_id: str,
    *,
    fixture_only: bool,
) -> XbrlFact:
    return XbrlFact(
        fact_id=fact.fact_id,
        company_id=company_id,
        source_document_id=source_document_id,
        taxonomy=fact.taxonomy,
        concept=fact.concept,
        label=fact.label,
        unit=fact.unit,
        value=fact.value,
        end_date=fact.end_date,
        filed_date=fact.filed_date,
        frame=fact.frame,
        accession_number=fact.accession_number,
        form=fact.form,
        fiscal_year=fact.fiscal_year,
        fiscal_period=fact.fiscal_period,
        confidence="high_official_sec_edgar_public_api",
        fixture_only=fixture_only,
    )


def _replace_claim_company_id(claim: EvidenceClaim, company_id: str) -> EvidenceClaim:
    return EvidenceClaim(
        claim_id=claim.claim_id,
        company_id=company_id,
        source_document_id=claim.source_document_id,
        fact_id=claim.fact_id,
        claim_type=claim.claim_type,
        claim_text=claim.claim_text,
        source_date=claim.source_date,
        confidence=claim.confidence,
        review_status=claim.review_status,
        fixture_only=claim.fixture_only,
    )


def _merge_company(primary: CompanyRef, secondary: CompanyRef) -> CompanyRef:
    if primary.cik:
        return primary
    return secondary


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _recent_row_count(recent: dict[str, Any]) -> int:
    lengths = [len(value) for value in recent.values() if isinstance(value, list)]
    return max(lengths) if lengths else 0


def _recent_value(recent: dict[str, Any], key: str, index: int) -> str:
    values = recent.get(key)
    if not isinstance(values, list) or index >= len(values):
        return ""
    value = values[index]
    return "" if value is None else str(value)


def _max_recent_date(recent: dict[str, Any], key: str) -> str:
    values = recent.get(key)
    if not isinstance(values, list):
        return ""
    dates = sorted(str(value) for value in values if value)
    return dates[-1] if dates else ""


def _max_companyfacts_date(payload: dict[str, Any]) -> str:
    dates: list[str] = []
    for taxonomy_payload in _safe_dict(payload.get("facts")).values():
        for concept_payload in _safe_dict(taxonomy_payload).values():
            for unit_facts in _safe_dict(_safe_dict(concept_payload).get("units")).values():
                if not isinstance(unit_facts, list):
                    continue
                for fact_payload in unit_facts:
                    filed = _safe_dict(fact_payload).get("filed")
                    if filed:
                        dates.append(str(filed))
    return sorted(dates)[-1] if dates else ""


def _hash_file(path: Path) -> str:
    return _hash_text(path.read_text(encoding="utf-8"))


def _hash_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _pad_cik(cik: str) -> str:
    digits = "".join(character for character in cik if character.isdigit())
    return digits.zfill(10) if digits else ""


def _sec_endpoint_reference(cik: str, source_type: str) -> str:
    cik_padded = _pad_cik(cik)
    if not cik_padded:
        return ""
    if source_type == "sec_companyfacts_fixture":
        return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"
    return f"https://data.sec.gov/submissions/CIK{cik_padded}.json"


def _sec_archive_url(cik: str, accession_number: str, primary_document: str) -> str:
    cik_digits = str(int(cik)) if str(cik).isdigit() else str(cik).lstrip("0")
    accession_digits = accession_number.replace("-", "")
    if not cik_digits or not accession_digits or not primary_document:
        return ""
    return f"https://www.sec.gov/Archives/edgar/data/{cik_digits}/{accession_digits}/{primary_document}"


def _numeric_value(raw_value: Any) -> float | None:
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None


def _optional_int(raw_value: Any) -> int | None:
    if raw_value is None or raw_value == "":
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
