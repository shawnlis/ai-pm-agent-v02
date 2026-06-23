"""Read-only live provider permission checks for autopm.

This module defines the boundary for future opt-in live providers. It does not
fetch data, connect to brokers, read account files, or enable live
recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlparse


LEVEL_1_PUBLIC_OFFICIAL_READ_ONLY = "LEVEL_1_PUBLIC_OFFICIAL_READ_ONLY"
LEVEL_2_MARKET_DATA_VENDOR_READ_ONLY = "LEVEL_2_MARKET_DATA_VENDOR_READ_ONLY"

ALLOWED_READ_ONLY_PROVIDER_LEVELS = frozenset(
    {
        LEVEL_1_PUBLIC_OFFICIAL_READ_ONLY,
        LEVEL_2_MARKET_DATA_VENDOR_READ_ONLY,
    }
)
READ_ONLY_METHODS = frozenset({"GET", "HEAD"})
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
FORBIDDEN_PATH_TERMS = (
    ".env",
    "openrouter.txt",
    "api_key",
    "token",
    "credential",
    "secret",
    "cookie",
    "session",
    "portfolio.csv",
    "ibkr",
    "moomoo",
    "webull",
    "bank",
    "custodian",
    "broker",
    "client",
    "account",
    "statement",
)
FORBIDDEN_SCAN_SEGMENTS = frozenset({"reports", "outputs"})


class LiveProviderPermission(StrEnum):
    READ_ONLY_HTTP = "READ_ONLY_HTTP"


@dataclass(frozen=True)
class ReadOnlyLiveProviderConfig:
    allow_live_fetch: bool = False
    offline: bool = True
    provider_name: str = ""
    provider_level: str = ""
    allowed_domains: tuple[str, ...] = ()
    user_agent: str = ""
    requires_user_agent: bool = True
    cache_enabled: bool = False
    cache_dir: str = ""
    allow_local_fixture_url: bool = False


@dataclass(frozen=True)
class LiveProviderPolicyResult:
    allowed: bool
    provider_name: str
    provider_level: str
    permission: LiveProviderPermission = LiveProviderPermission.READ_ONLY_HTTP
    normalized_url: str = ""
    domain: str = ""
    warning_codes: tuple[str, ...] = ()
    error_codes: tuple[str, ...] = ()


class LiveProviderPolicyError(ValueError):
    """Raised when a read-only live provider request fails closed."""


def evaluate_live_provider_request(
    config: ReadOnlyLiveProviderConfig,
    *,
    url: str,
    method: str = "GET",
) -> LiveProviderPolicyResult:
    """Return a fail-closed policy decision for one provider request."""

    errors: list[str] = []
    warnings: list[str] = []
    method_upper = method.upper().strip()
    parsed = urlparse(url)
    domain = (parsed.hostname or "").lower()

    if config.offline:
        errors.append("OFFLINE_MODE_BLOCKS_LIVE_PROVIDER")
    if not config.allow_live_fetch:
        errors.append("LIVE_FETCH_DISABLED")
    if not _text(config.provider_name):
        errors.append("PROVIDER_NAME_MISSING")
    if not _text(config.provider_level):
        errors.append("PROVIDER_LEVEL_MISSING")
    elif config.provider_level not in ALLOWED_READ_ONLY_PROVIDER_LEVELS:
        errors.append("PROVIDER_LEVEL_NOT_READ_ONLY_ALLOWED")
    if not config.allowed_domains:
        errors.append("ALLOWED_DOMAINS_MISSING")
    if method_upper in MUTATING_METHODS or method_upper not in READ_ONLY_METHODS:
        errors.append("MUTATING_HTTP_METHOD_FORBIDDEN")
    if config.requires_user_agent and not _text(config.user_agent):
        errors.append("USER_AGENT_REQUIRED")

    if not _scheme_allowed(parsed.scheme, config.allow_local_fixture_url):
        errors.append("NON_HTTPS_URL_FORBIDDEN")
    if parsed.scheme in {"http", "https"} and not domain:
        errors.append("URL_DOMAIN_MISSING")
    if domain and config.allowed_domains and not _domain_allowed(domain, config.allowed_domains):
        errors.append("DOMAIN_NOT_ALLOWLISTED")
    if _looks_private_or_broker_like(url):
        errors.append("BROKER_ACCOUNT_CLIENT_PATH_FORBIDDEN")
    if _contains_forbidden_scan_segment(parsed.path):
        errors.append("IMPLICIT_REPORTS_OUTPUTS_SCAN_FORBIDDEN")

    if config.cache_enabled:
        if not _text(config.cache_dir):
            errors.append("CACHE_DIR_REQUIRED")
        elif _looks_private_or_broker_like(config.cache_dir) or _contains_forbidden_scan_segment(config.cache_dir):
            errors.append("CACHE_DIR_FORBIDDEN")
    elif _text(config.cache_dir):
        warnings.append("CACHE_DIR_IGNORED_WHEN_CACHE_DISABLED")

    return LiveProviderPolicyResult(
        allowed=not errors,
        provider_name=_text(config.provider_name),
        provider_level=_text(config.provider_level),
        normalized_url=url.strip(),
        domain=domain,
        warning_codes=tuple(sorted(set(warnings))),
        error_codes=tuple(sorted(set(errors))),
    )


def assert_live_provider_allowed(
    config: ReadOnlyLiveProviderConfig,
    *,
    url: str,
    method: str = "GET",
) -> LiveProviderPolicyResult:
    """Return the policy result or raise a fail-closed error."""

    result = evaluate_live_provider_request(config, url=url, method=method)
    if not result.allowed:
        raise LiveProviderPolicyError(";".join(result.error_codes))
    return result


def allowed_domain_for_url(url: str) -> str:
    """Return the normalized host for tests and provider manifests."""

    return (urlparse(url).hostname or "").lower()


def validate_cache_dir(cache_dir: str) -> Path:
    """Validate cache directory text without scanning or reading it."""

    if _looks_private_or_broker_like(cache_dir) or _contains_forbidden_scan_segment(cache_dir):
        raise LiveProviderPolicyError("CACHE_DIR_FORBIDDEN")
    return Path(cache_dir)


def _scheme_allowed(scheme: str, allow_local_fixture_url: bool) -> bool:
    if scheme == "https":
        return True
    if allow_local_fixture_url and scheme in {"file", ""}:
        return True
    return False


def _domain_allowed(domain: str, allowed_domains: tuple[str, ...]) -> bool:
    normalized = tuple(item.lower().strip() for item in allowed_domains if item.strip())
    return any(domain == item or domain.endswith(f".{item}") for item in normalized)


def _looks_private_or_broker_like(value: str) -> bool:
    lowered = value.lower()
    return any(term in lowered for term in FORBIDDEN_PATH_TERMS)


def _contains_forbidden_scan_segment(value: str) -> bool:
    parts = [part.strip().lower() for part in value.replace("\\", "/").split("/") if part.strip()]
    return any(part in FORBIDDEN_SCAN_SEGMENTS for part in parts)


def _text(value: object) -> str:
    return str(value or "").strip()
