"""Read-only live provider shell for autopm.

The provider shell is default-off and transport-injected. It does not integrate
with ranking, recommendation, rebalance, monitor, scheduler, broker, or
execution flows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from ai_pm_agent.autopm.live_provider_policy import (
    ReadOnlyLiveProviderConfig,
    assert_live_provider_allowed,
    validate_cache_dir,
)
from ai_pm_agent.autopm.models import AUTOPM_SCHEMA_VERSION


Transport = Callable[["ReadOnlyProviderRequest"], "ReadOnlyProviderResponse"]


class LiveProviderError(ValueError):
    """Raised when a read-only provider fails closed."""


@dataclass(frozen=True)
class ReadOnlyProviderRequest:
    url: str
    method: str = "GET"
    headers: dict[str, str] | None = None


@dataclass(frozen=True)
class ReadOnlyProviderResponse:
    status_code: int
    body: str
    headers: dict[str, str] | None = None


@dataclass(frozen=True)
class ReadOnlyProviderResult:
    provider_name: str
    provider_level: str
    retrieval_time: str
    as_of_date: str
    source_url: str
    source_hash: str
    payload: Any
    cache_path: str = ""
    stale: bool = False
    warning_codes: tuple[str, ...] = ()
    read_only: bool = True
    not_broker_data: bool = True
    not_execution_capable: bool = True
    schema_version: str = AUTOPM_SCHEMA_VERSION

    def to_manifest(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provider_name": self.provider_name,
            "provider_level": self.provider_level,
            "retrieval_time": self.retrieval_time,
            "as_of_date": self.as_of_date,
            "source_url": self.source_url,
            "source_hash": self.source_hash,
            "cache_path": self.cache_path,
            "stale": self.stale,
            "warning_codes": list(self.warning_codes),
            "read_only": self.read_only,
            "not_broker_data": self.not_broker_data,
            "not_execution_capable": self.not_execution_capable,
        }

    def to_dict(self) -> dict[str, Any]:
        row = self.to_manifest()
        row["payload"] = self.payload
        return row


class OfficialPublicReadOnlyProvider:
    """Minimal official/public read-only provider with injected transport."""

    def __init__(
        self,
        config: ReadOnlyLiveProviderConfig,
        *,
        transport: Transport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport or _default_refusing_transport

    def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        as_of_date: str | None = None,
        stale: bool = False,
        warning_codes: tuple[str, ...] = (),
    ) -> ReadOnlyProviderResult:
        decision = assert_live_provider_allowed(self.config, url=url, method=method)
        request = ReadOnlyProviderRequest(
            url=decision.normalized_url,
            method=method.upper().strip(),
            headers={"User-Agent": self.config.user_agent} if self.config.user_agent else {},
        )
        response = self.transport(request)
        if response.status_code < 200 or response.status_code >= 300:
            raise LiveProviderError(f"provider returned HTTP {response.status_code}")
        payload = _parse_payload(response.body)
        source_hash = compute_source_hash(decision.normalized_url, response.body)
        cache_path = _write_cache_if_enabled(self.config, source_hash, response.body)
        retrieval_time = datetime.now(UTC).replace(microsecond=0).isoformat()
        return ReadOnlyProviderResult(
            provider_name=decision.provider_name,
            provider_level=decision.provider_level,
            retrieval_time=retrieval_time,
            as_of_date=as_of_date or date.today().isoformat(),
            source_url=decision.normalized_url,
            source_hash=source_hash,
            payload=payload,
            cache_path=cache_path,
            stale=stale,
            warning_codes=tuple(sorted(set(warning_codes + decision.warning_codes))),
        )


def compute_source_hash(source_url: str, body: str) -> str:
    """Return a deterministic hash over source identity and payload."""

    material = f"{source_url.strip()}\n{_canonical_body(body)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _default_refusing_transport(request: ReadOnlyProviderRequest) -> ReadOnlyProviderResponse:
    raise LiveProviderError("default live transport is disabled; inject an approved read-only transport")


def _parse_payload(body: str) -> Any:
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body


def _canonical_body(body: str) -> str:
    parsed = _parse_payload(body)
    if isinstance(parsed, (dict, list)):
        return json.dumps(parsed, sort_keys=True, separators=(",", ":"))
    return body


def _write_cache_if_enabled(config: ReadOnlyLiveProviderConfig, source_hash: str, body: str) -> str:
    if not config.cache_enabled:
        return ""
    cache_dir = validate_cache_dir(config.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{source_hash}.json"
    cache_path.write_text(body, encoding="utf-8")
    return str(cache_path)
