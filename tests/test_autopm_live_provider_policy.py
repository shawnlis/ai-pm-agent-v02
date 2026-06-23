from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.autopm.live_provider_policy import (
    LEVEL_1_PUBLIC_OFFICIAL_READ_ONLY,
    LEVEL_2_MARKET_DATA_VENDOR_READ_ONLY,
    ReadOnlyLiveProviderConfig,
    evaluate_live_provider_request,
)


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


def test_default_config_disables_live_fetch() -> None:
    result = evaluate_live_provider_request(ReadOnlyLiveProviderConfig(), url="https://data.sec.gov/submissions/CIK0000000000.json")

    assert result.allowed is False
    assert "LIVE_FETCH_DISABLED" in result.error_codes


def test_offline_mode_fails_closed() -> None:
    result = evaluate_live_provider_request(_config(offline=True), url="https://data.sec.gov/submissions/CIK0000000000.json")

    assert result.allowed is False
    assert "OFFLINE_MODE_BLOCKS_LIVE_PROVIDER" in result.error_codes


def test_allow_live_fetch_false_fails_closed() -> None:
    result = evaluate_live_provider_request(_config(allow_live_fetch=False), url="https://data.sec.gov/submissions/CIK0000000000.json")

    assert result.allowed is False
    assert "LIVE_FETCH_DISABLED" in result.error_codes


def test_mutating_method_rejected() -> None:
    result = evaluate_live_provider_request(_config(), url="https://data.sec.gov/submissions/CIK0000000000.json", method="POST")

    assert result.allowed is False
    assert "MUTATING_HTTP_METHOD_FORBIDDEN" in result.error_codes


def test_non_allowlisted_domain_rejected() -> None:
    result = evaluate_live_provider_request(_config(), url="https://example.com/submissions/CIK0000000000.json")

    assert result.allowed is False
    assert "DOMAIN_NOT_ALLOWLISTED" in result.error_codes


def test_broker_account_ibkr_looking_url_rejected() -> None:
    result = evaluate_live_provider_request(_config(allowed_domains=("data.sec.gov",)), url="https://data.sec.gov/IBKR/account/statement.json")

    assert result.allowed is False
    assert "BROKER_ACCOUNT_CLIENT_PATH_FORBIDDEN" in result.error_codes


def test_missing_provider_metadata_rejected() -> None:
    result = evaluate_live_provider_request(
        _config(provider_name="", provider_level="", allowed_domains=()),
        url="https://data.sec.gov/submissions/CIK0000000000.json",
    )

    assert result.allowed is False
    assert "PROVIDER_NAME_MISSING" in result.error_codes
    assert "PROVIDER_LEVEL_MISSING" in result.error_codes
    assert "ALLOWED_DOMAINS_MISSING" in result.error_codes


def test_missing_user_agent_rejected_where_required() -> None:
    result = evaluate_live_provider_request(_config(user_agent=""), url="https://data.sec.gov/submissions/CIK0000000000.json")

    assert result.allowed is False
    assert "USER_AGENT_REQUIRED" in result.error_codes


def test_non_https_rejected_for_live_provider() -> None:
    result = evaluate_live_provider_request(_config(), url="http://data.sec.gov/submissions/CIK0000000000.json")

    assert result.allowed is False
    assert "NON_HTTPS_URL_FORBIDDEN" in result.error_codes


def test_cache_reports_outputs_scan_rejected(tmp_path: Path) -> None:
    result = evaluate_live_provider_request(
        _config(cache_enabled=True, cache_dir=str(tmp_path / "reports" / "cache")),
        url="https://data.sec.gov/submissions/CIK0000000000.json",
    )

    assert result.allowed is False
    assert "CACHE_DIR_FORBIDDEN" in result.error_codes


def test_market_data_vendor_level_supported() -> None:
    result = evaluate_live_provider_request(
        _config(
            provider_name="market_vendor",
            provider_level=LEVEL_2_MARKET_DATA_VENDOR_READ_ONLY,
            allowed_domains=("api.vendor.example",),
            requires_user_agent=False,
            user_agent="",
        ),
        url="https://api.vendor.example/market/snapshot",
        method="HEAD",
    )

    assert result.allowed is True
