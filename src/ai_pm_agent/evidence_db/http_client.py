"""Small stdlib HTTP client for explicit SEC EDGAR Level 1 fetches."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import utc_now
from .warnings import (
    SEC_HTTP_ERROR,
    SEC_INVALID_RESPONSE,
    SEC_RATE_LIMIT_OR_RETRY_EXHAUSTED,
    SEC_USER_AGENT_REQUIRED,
)


DEFAULT_TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class HttpJsonResponse:
    url: str
    payload: Any
    raw_text: str
    sha256: str
    retrieved_at: str
    status_code: int


class SecHttpError(RuntimeError):
    """Fail-closed SEC HTTP error with a structured warning code."""

    def __init__(self, code: str, message: str, *, url: str = "", status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.url = url
        self.status_code = status_code


def fetch_json(url: str, user_agent: str, *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> HttpJsonResponse:
    """Fetch and parse JSON from a public SEC endpoint with explicit User-Agent."""

    clean_user_agent = user_agent.strip() if user_agent else ""
    if not clean_user_agent:
        raise SecHttpError(SEC_USER_AGENT_REQUIRED, "SEC EDGAR live fetch requires --sec-user-agent.", url=url)

    request = Request(
        url,
        headers={
            "User-Agent": clean_user_agent,
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            status_code = int(response.getcode() or 200)
            raw_bytes = response.read()
    except HTTPError as exc:
        code = SEC_RATE_LIMIT_OR_RETRY_EXHAUSTED if exc.code in {403, 429} else SEC_HTTP_ERROR
        raise SecHttpError(
            code,
            f"SEC EDGAR HTTP request failed with status {exc.code}.",
            url=url,
            status_code=exc.code,
        ) from exc
    except URLError as exc:
        raise SecHttpError(SEC_HTTP_ERROR, f"SEC EDGAR HTTP request failed: {exc.reason}", url=url) from exc

    if status_code >= 400:
        code = SEC_RATE_LIMIT_OR_RETRY_EXHAUSTED if status_code in {403, 429} else SEC_HTTP_ERROR
        raise SecHttpError(code, f"SEC EDGAR HTTP request failed with status {status_code}.", url=url, status_code=status_code)

    raw_text = raw_bytes.decode("utf-8")
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise SecHttpError(SEC_INVALID_RESPONSE, "SEC EDGAR response was not valid JSON.", url=url, status_code=status_code) from exc

    return HttpJsonResponse(
        url=url,
        payload=payload,
        raw_text=raw_text,
        sha256=hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        retrieved_at=utc_now(),
        status_code=status_code,
    )
