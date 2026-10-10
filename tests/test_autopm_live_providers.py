from __future__ import annotations

import hashlib
import json
from pathlib import Path
import socket
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.autopm.live_provider_policy import (
    LEVEL_1_PUBLIC_OFFICIAL_READ_ONLY,
    ReadOnlyLiveProviderConfig,
)
from ai_pm_agent.autopm.live_providers import (
    LiveProviderError,
    OfficialPublicReadOnlyProvider,
    ReadOnlyProviderRequest,
    ReadOnlyProviderResponse,
    compute_source_hash,
)
from ai_pm_agent.autopm.models import AUTOPM_SCHEMA_VERSION


def _config(**overrides: object) -> ReadOnlyLiveProviderConfig:
    values = {
        "allow_live_fetch": True,
        "offline": False,
        "provider_name": "sec_public",
        "provider_level": LEVEL_1_PUBLIC_OFFICIAL_READ_ONLY,
        "allowed_domains": ("data.sec.gov",),
        "user_agent": "ai-pm-agent-test contact@example.com",
    }
    values.update(overrides)
    return ReadOnlyLiveProviderConfig(**values)


def test_fake_injectable_transport_returns_manifest_without_network() -> None:
    calls: list[ReadOnlyProviderRequest] = []

    def fake_transport(request: ReadOnlyProviderRequest) -> ReadOnlyProviderResponse:
        calls.append(request)
        return ReadOnlyProviderResponse(status_code=200, body='{"ticker":"CAMT","revenue":123}')

    provider = OfficialPublicReadOnlyProvider(_config(), transport=fake_transport)
    result = provider.fetch("https://data.sec.gov/submissions/CIK0000000000.json", as_of_date="2026-06-23")
    manifest = result.to_manifest()

    assert calls and calls[0].method == "GET"
    assert calls[0].headers == {"User-Agent": "ai-pm-agent-test contact@example.com"}
    assert manifest["schema_version"] == AUTOPM_SCHEMA_VERSION
    assert manifest["provider_name"] == "sec_public"
    assert manifest["provider_level"] == LEVEL_1_PUBLIC_OFFICIAL_READ_ONLY
    assert manifest["as_of_date"] == "2026-06-23"
    assert manifest["source_url"] == "https://data.sec.gov/submissions/CIK0000000000.json"
    assert len(manifest["source_hash"]) == 64
    assert manifest["read_only"] is True
    assert manifest["not_broker_data"] is True
    assert manifest["not_execution_capable"] is True
    assert result.payload == {"ticker": "CAMT", "revenue": 123}


def test_source_hash_is_deterministic_for_exact_raw_response() -> None:
    first = compute_source_hash("https://data.sec.gov/a.json", '{"b":2,"a":1}')
    second = compute_source_hash("https://data.sec.gov/a.json", '{ "a": 1, "b": 2 }')

    assert first != second
    assert first == hashlib.sha256(b'{"b":2,"a":1}').hexdigest()
    assert first == compute_source_hash("https://data.sec.gov/a.json", b'{"b":2,"a":1}')


def test_default_transport_refuses_network_even_when_config_enabled() -> None:
    provider = OfficialPublicReadOnlyProvider(_config())

    with pytest.raises(LiveProviderError, match="default live transport is disabled"):
        provider.fetch("https://data.sec.gov/submissions/CIK0000000000.json")


def test_provider_policy_blocks_offline_before_transport() -> None:
    def fail_transport(request: ReadOnlyProviderRequest) -> ReadOnlyProviderResponse:
        raise AssertionError("offline policy should block before transport")

    provider = OfficialPublicReadOnlyProvider(_config(offline=True), transport=fail_transport)

    with pytest.raises(ValueError, match="OFFLINE_MODE_BLOCKS_LIVE_PROVIDER"):
        provider.fetch("https://data.sec.gov/submissions/CIK0000000000.json")


def test_provider_policy_blocks_mutating_method_before_transport() -> None:
    def fail_transport(request: ReadOnlyProviderRequest) -> ReadOnlyProviderResponse:
        raise AssertionError("mutating method should block before transport")

    provider = OfficialPublicReadOnlyProvider(_config(), transport=fail_transport)

    with pytest.raises(ValueError, match="MUTATING_HTTP_METHOD_FORBIDDEN"):
        provider.fetch("https://data.sec.gov/submissions/CIK0000000000.json", method="DELETE")


def test_cache_path_written_only_to_tempdir_when_explicit(tmp_path: Path) -> None:
    def fake_transport(request: ReadOnlyProviderRequest) -> ReadOnlyProviderResponse:
        return ReadOnlyProviderResponse(status_code=200, body='{"ok":true}')

    cache_dir = tmp_path / "safe-cache"
    provider = OfficialPublicReadOnlyProvider(_config(cache_enabled=True, cache_dir=str(cache_dir)), transport=fake_transport)
    result = provider.fetch("https://data.sec.gov/submissions/CIK0000000000.json", as_of_date="2026-06-23")

    assert result.cache_path
    cache_path = Path(result.cache_path)
    assert cache_path.exists()
    assert cache_path.parent == cache_dir
    assert json.loads(cache_path.read_text(encoding="utf-8")) == {"ok": True}


def test_non_2xx_response_fails_closed() -> None:
    def fake_transport(request: ReadOnlyProviderRequest) -> ReadOnlyProviderResponse:
        return ReadOnlyProviderResponse(status_code=503, body="unavailable")

    provider = OfficialPublicReadOnlyProvider(_config(), transport=fake_transport)

    with pytest.raises(LiveProviderError, match="HTTP 503"):
        provider.fetch("https://data.sec.gov/submissions/CIK0000000000.json")


def test_no_network_access_required(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked_socket(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", blocked_socket)

    def fake_transport(request: ReadOnlyProviderRequest) -> ReadOnlyProviderResponse:
        return ReadOnlyProviderResponse(status_code=200, body='{"ok":true}')

    provider = OfficialPublicReadOnlyProvider(_config(), transport=fake_transport)
    assert provider.fetch("https://data.sec.gov/submissions/CIK0000000000.json").payload == {"ok": True}


def test_no_ranking_recommender_rebalance_or_broker_execution_imports() -> None:
    offenders: list[str] = []
    forbidden = (
        "stock_picker",
        "asia_ai_hardware",
        "recommender",
        "sizing",
        "rebalance",
        "report_writer",
        "portfolio_loader",
        "portfolio_policy",
        "broker",
        "ibkr",
        "execution",
        "yfinance",
        "openrouter",
        "deepseek",
    )
    for path in [
        SRC / "ai_pm_agent" / "autopm" / "live_provider_policy.py",
        SRC / "ai_pm_agent" / "autopm" / "live_providers.py",
    ]:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip().lower()
            if stripped.startswith(("import ", "from ")) and any(term in stripped for term in forbidden):
                offenders.append(f"{path}:{line}")

    assert offenders == []


def test_no_implicit_reports_outputs_scan_or_generated_committed_files() -> None:
    tracked = subprocess_output(["git", "ls-files", "reports", "outputs"])

    assert tracked == ""


def subprocess_output(args: list[str]) -> str:
    import subprocess

    result = subprocess.run(args, cwd=ROOT, check=True, capture_output=True, text=True)
    return result.stdout.strip()


@pytest.mark.parametrize("body", ["not-json", b"not-json", b"{", b"", b"\xff", b"NaN", b"Infinity", b"-Infinity"])
def test_invalid_json_fails_closed_without_cache(body: bytes | str, tmp_path: Path) -> None:
    cache_dir = tmp_path / "safe-cache"
    provider = OfficialPublicReadOnlyProvider(
        _config(cache_enabled=True, cache_dir=str(cache_dir)),
        transport=lambda request: ReadOnlyProviderResponse(200, body),
    )
    with pytest.raises(LiveProviderError, match="invalid JSON"):
        provider.fetch("https://data.sec.gov/a.json")
    assert not cache_dir.exists()


def test_raw_bytes_and_cache_remain_byte_identical(tmp_path: Path) -> None:
    raw = b'{\r\n  "label": "\xc3\xa9", "n": 2\r\n}\n'
    provider = OfficialPublicReadOnlyProvider(
        _config(cache_enabled=True, cache_dir=str(tmp_path / "safe-cache")),
        transport=lambda request: ReadOnlyProviderResponse(200, raw),
    )
    result = provider.fetch("https://data.sec.gov/a.json")
    assert result.payload == {"label": "é", "n": 2}
    assert result.source_hash == hashlib.sha256(raw).hexdigest()
    assert Path(result.cache_path).read_bytes() == raw
    assert result.source_url == "https://data.sec.gov/a.json"


def test_json_scalars_remain_valid_and_head_needs_no_json_body() -> None:
    provider = OfficialPublicReadOnlyProvider(
        _config(), transport=lambda request: ReadOnlyProviderResponse(200, b"true"),
    )
    assert provider.fetch("https://data.sec.gov/a.json").payload is True
    provider = OfficialPublicReadOnlyProvider(
        _config(), transport=lambda request: ReadOnlyProviderResponse(200, b""),
    )
    result = provider.fetch("https://data.sec.gov/a.json", method="HEAD")
    assert result.payload is None
    assert result.source_hash == hashlib.sha256(b"").hexdigest()


@pytest.mark.parametrize("url", ["https://evil.data.sec.gov/a.json", "https://data.sec.gov:444/a.json"])
def test_rejected_endpoint_never_reaches_transport(url: str) -> None:
    def forbidden(request: ReadOnlyProviderRequest) -> ReadOnlyProviderResponse:
        raise AssertionError("rejected endpoints cannot reach transport")
    provider = OfficialPublicReadOnlyProvider(_config(), transport=forbidden)
    with pytest.raises(ValueError, match="DOMAIN_NOT_ALLOWLISTED|URL_PORT_NOT_ALLOWED"):
        provider.fetch(url)
