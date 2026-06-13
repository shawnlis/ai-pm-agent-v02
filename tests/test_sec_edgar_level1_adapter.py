from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.evidence_db import http_client
from ai_pm_agent.evidence_db.http_client import HttpJsonResponse, SecHttpError
from ai_pm_agent.evidence_db.sec_edgar import (
    fetch_sec_companyfacts,
    fetch_sec_submissions,
    import_live_sec,
    resolve_cik_from_ticker,
)
from ai_pm_agent.evidence_db.warnings import (
    SEC_CACHE_HIT,
    SEC_CACHE_MISS,
    SEC_FETCH_FAIL_CLOSED,
    SEC_HTTP_ERROR,
    SEC_INVALID_RESPONSE,
)


SUBMISSIONS_FIXTURE = ROOT / "tests" / "fixtures" / "sec_edgar" / "MU_submissions_sample.json"
COMPANYFACTS_FIXTURE = ROOT / "tests" / "fixtures" / "sec_edgar" / "MU_companyfacts_sample.json"
SCRIPT = ROOT / "scripts" / "sec_ir_evidence_import.py"
USER_AGENT = "Unit Test unit@example.com"


def _payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _response(url: str, payload: object, retrieved_at: str = "2026-06-13T00:00:00+00:00") -> HttpJsonResponse:
    raw_text = json.dumps(payload, sort_keys=True)
    return HttpJsonResponse(
        url=url,
        payload=payload,
        raw_text=raw_text,
        sha256=hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        retrieved_at=retrieved_at,
        status_code=200,
    )


def test_live_sec_fetch_requires_user_agent() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--ticker",
                "MU",
                "--company-name",
                "Micron Technology",
                "--live-sec-fetch",
                "--out-dir",
                str(Path(tmp) / "out"),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    assert result.returncode != 0
    assert "--sec-user-agent" in result.stderr


def test_offline_blocks_live_sec_fetch() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--ticker",
                "MU",
                "--company-name",
                "Micron Technology",
                "--live-sec-fetch",
                "--sec-user-agent",
                USER_AGENT,
                "--offline",
                "--out-dir",
                str(Path(tmp) / "out"),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    assert result.returncode != 0
    assert "--offline blocks --live-sec-fetch" in result.stderr


def test_cik_resolution_uses_mocked_sec_company_ticker_json(monkeypatch) -> None:
    calls: list[str] = []

    def fake_fetch(url: str, user_agent: str):
        calls.append(url)
        return _response(url, {"0": {"cik_str": 723125, "ticker": "MU", "title": "Micron Technology"}})

    monkeypatch.setattr(http_client, "fetch_json", fake_fetch)
    with tempfile.TemporaryDirectory() as tmp:
        cik = resolve_cik_from_ticker("MU", Path(tmp) / "cache", USER_AGENT)

    assert cik == "723125"
    assert len(calls) == 1
    assert calls[0].endswith("/company_tickers.json")


def test_submissions_fetch_uses_mocked_http_response(monkeypatch) -> None:
    payload = _payload(SUBMISSIONS_FIXTURE)

    def fake_fetch(url: str, user_agent: str):
        return _response(url, payload)

    monkeypatch.setattr(http_client, "fetch_json", fake_fetch)
    with tempfile.TemporaryDirectory() as tmp:
        result = fetch_sec_submissions("723125", USER_AGENT, Path(tmp) / "cache")

    assert result.payload["cik"] == "723125"
    assert result.cache_path.name == "submissions_0000723125.json"
    assert result.cache_hit is False


def test_companyfacts_fetch_uses_mocked_http_response(monkeypatch) -> None:
    payload = _payload(COMPANYFACTS_FIXTURE)

    def fake_fetch(url: str, user_agent: str):
        return _response(url, payload)

    monkeypatch.setattr(http_client, "fetch_json", fake_fetch)
    with tempfile.TemporaryDirectory() as tmp:
        result = fetch_sec_companyfacts("723125", USER_AGENT, Path(tmp) / "cache")

    assert result.payload["entityName"] == "Micron Technology"
    assert result.cache_path.name == "companyfacts_0000723125.json"
    assert result.cache_hit is False


def test_cache_hit_avoids_network(monkeypatch) -> None:
    payload = _payload(SUBMISSIONS_FIXTURE)
    calls = 0

    def fake_fetch(url: str, user_agent: str):
        nonlocal calls
        calls += 1
        return _response(url, payload)

    with tempfile.TemporaryDirectory() as tmp:
        cache_dir = Path(tmp) / "cache"
        monkeypatch.setattr(http_client, "fetch_json", fake_fetch)
        first = fetch_sec_submissions("723125", USER_AGENT, cache_dir)

        def fail_fetch(url: str, user_agent: str):
            raise AssertionError("cache hit should not fetch")

        monkeypatch.setattr(http_client, "fetch_json", fail_fetch)
        second = fetch_sec_submissions("723125", USER_AGENT, cache_dir)

    assert calls == 1
    assert first.cache_hit is False
    assert second.cache_hit is True


def test_force_refresh_bypasses_cache(monkeypatch) -> None:
    payload = _payload(SUBMISSIONS_FIXTURE)
    calls = 0

    def fake_fetch(url: str, user_agent: str):
        nonlocal calls
        calls += 1
        return _response(url, payload, retrieved_at=f"2026-06-13T00:00:0{calls}+00:00")

    monkeypatch.setattr(http_client, "fetch_json", fake_fetch)
    with tempfile.TemporaryDirectory() as tmp:
        cache_dir = Path(tmp) / "cache"
        fetch_sec_submissions("723125", USER_AGENT, cache_dir)
        refreshed = fetch_sec_submissions("723125", USER_AGENT, cache_dir, force_refresh=True)

    assert calls == 2
    assert refreshed.cache_hit is False
    assert refreshed.retrieved_at.endswith("02+00:00")


def test_http_failure_fails_closed_and_writes_warning(monkeypatch) -> None:
    def fail_fetch(url: str, user_agent: str):
        raise SecHttpError(SEC_HTTP_ERROR, "mocked HTTP failure", url=url, status_code=500)

    monkeypatch.setattr(http_client, "fetch_json", fail_fetch)
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "out"
        outputs = import_live_sec(
            ticker="MU",
            company_name="Micron Technology",
            user_agent=USER_AGENT,
            cik="723125",
            cache_dir=Path(tmp) / "cache",
            out_dir=out_dir,
        )
        warnings_md = (out_dir / "ingestion_warnings.md").read_text(encoding="utf-8")

    assert outputs["status"] == "failed"
    assert SEC_HTTP_ERROR in warnings_md
    assert SEC_FETCH_FAIL_CLOSED in warnings_md


def test_invalid_json_shape_fails_closed_and_writes_warning(monkeypatch) -> None:
    def invalid_fetch(url: str, user_agent: str):
        return _response(url, ["not", "an", "object"])

    monkeypatch.setattr(http_client, "fetch_json", invalid_fetch)
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "out"
        outputs = import_live_sec(
            ticker="MU",
            company_name="Micron Technology",
            user_agent=USER_AGENT,
            cik="723125",
            cache_dir=Path(tmp) / "cache",
            out_dir=out_dir,
        )
        warnings_md = (out_dir / "ingestion_warnings.md").read_text(encoding="utf-8")

    assert outputs["status"] == "failed"
    assert SEC_INVALID_RESPONSE in warnings_md
    assert SEC_FETCH_FAIL_CLOSED in warnings_md


def test_source_manifest_marks_live_mode_level1(monkeypatch) -> None:
    submissions = _payload(SUBMISSIONS_FIXTURE)
    companyfacts = _payload(COMPANYFACTS_FIXTURE)

    def fake_fetch(url: str, user_agent: str):
        if "companyfacts" in url:
            return _response(url, companyfacts)
        return _response(url, submissions)

    monkeypatch.setattr(http_client, "fetch_json", fake_fetch)
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "out"
        outputs = import_live_sec(
            ticker="MU",
            company_name="Micron Technology",
            user_agent=USER_AGENT,
            cik="723125",
            cache_dir=Path(tmp) / "cache",
            out_dir=out_dir,
        )
        manifest = json.loads((out_dir / "source_manifest.json").read_text(encoding="utf-8"))

    assert outputs["status"] == "completed"
    assert manifest["fixture_only"] is False
    assert manifest["api_level"] == "Level 1"
    assert manifest["network_access"] is True
    assert manifest["live_sec_api"] is True
    assert manifest["pm_prompt_wiring"] is False
    assert manifest["portfolio_data_used"] is False
    assert manifest["broker_data_used"] is False
    assert manifest["client_data_used"] is False
    assert SEC_CACHE_MISS in manifest["warning_codes"]


def test_source_manifest_includes_url_hash_retrieved_at_and_cache_path(monkeypatch) -> None:
    submissions = _payload(SUBMISSIONS_FIXTURE)
    companyfacts = _payload(COMPANYFACTS_FIXTURE)

    def fake_fetch(url: str, user_agent: str):
        if "companyfacts" in url:
            return _response(url, companyfacts)
        return _response(url, submissions)

    monkeypatch.setattr(http_client, "fetch_json", fake_fetch)
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "out"
        import_live_sec(
            ticker="MU",
            company_name="Micron Technology",
            user_agent=USER_AGENT,
            cik="723125",
            cache_dir=Path(tmp) / "cache",
            out_dir=out_dir,
        )
        manifest = json.loads((out_dir / "source_manifest.json").read_text(encoding="utf-8"))

    assert len(manifest["sources"]) == 2
    for source in manifest["sources"]:
        assert source["url_reference"].startswith("https://")
        assert len(source["hash_sha256"]) == 64
        assert source["retrieved_at"]
        assert source["cache_path"]
        assert source["source_type"] == "SEC_EDGAR_PUBLIC_API"


def test_cache_hit_warning_appears_in_live_manifest(monkeypatch) -> None:
    submissions = _payload(SUBMISSIONS_FIXTURE)
    companyfacts = _payload(COMPANYFACTS_FIXTURE)

    def fake_fetch(url: str, user_agent: str):
        if "companyfacts" in url:
            return _response(url, companyfacts)
        return _response(url, submissions)

    with tempfile.TemporaryDirectory() as tmp:
        cache_dir = Path(tmp) / "cache"
        monkeypatch.setattr(http_client, "fetch_json", fake_fetch)
        import_live_sec(
            ticker="MU",
            company_name="Micron Technology",
            user_agent=USER_AGENT,
            cik="723125",
            cache_dir=cache_dir,
            out_dir=Path(tmp) / "first",
        )

        def fail_fetch(url: str, user_agent: str):
            raise AssertionError("second import should read from cache")

        monkeypatch.setattr(http_client, "fetch_json", fail_fetch)
        out_dir = Path(tmp) / "second"
        import_live_sec(
            ticker="MU",
            company_name="Micron Technology",
            user_agent=USER_AGENT,
            cik="723125",
            cache_dir=cache_dir,
            out_dir=out_dir,
        )
        manifest = json.loads((out_dir / "source_manifest.json").read_text(encoding="utf-8"))

    assert SEC_CACHE_HIT in manifest["warning_codes"]
    assert manifest["cache_hit"] is True


def test_fixture_import_cli_still_passes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "out"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--ticker",
                "MU",
                "--company-name",
                "Micron Technology",
                "--submissions-fixture",
                str(SUBMISSIONS_FIXTURE),
                "--companyfacts-fixture",
                str(COMPANYFACTS_FIXTURE),
                "--out-dir",
                str(out_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    assert result.returncode == 0, result.stderr
