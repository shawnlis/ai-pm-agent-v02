"""Local raw JSON cache for SEC EDGAR Level 1 public API responses."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from .http_client import HttpJsonResponse
from .models import utc_now


DEFAULT_SEC_CACHE_DIR = Path("reports") / "sec_ir_evidence_db" / "sec_cache"


@dataclass(frozen=True)
class CachedSecJson:
    payload: Any
    url: str
    cache_path: Path
    metadata_path: Path
    sha256: str
    retrieved_at: str
    cache_hit: bool
    api_level: str = "Level 1"
    source_type: str = "SEC_EDGAR_PUBLIC_API"


def cache_paths(cache_dir: Path | str, cache_name: str) -> tuple[Path, Path]:
    directory = Path(cache_dir)
    return directory / cache_name, directory / f"{Path(cache_name).stem}.meta.json"


def read_cached_json(cache_dir: Path | str, cache_name: str, *, url: str) -> CachedSecJson | None:
    cache_path, metadata_path = cache_paths(cache_dir, cache_name)
    if not cache_path.exists():
        return None
    raw_text = cache_path.read_text(encoding="utf-8")
    payload = json.loads(raw_text)
    metadata = _read_metadata(metadata_path)
    return CachedSecJson(
        payload=payload,
        url=str(metadata.get("source_url") or url),
        cache_path=cache_path,
        metadata_path=metadata_path,
        sha256=hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        retrieved_at=str(metadata.get("retrieved_at") or utc_now()),
        cache_hit=True,
    )


def write_cached_json(cache_dir: Path | str, cache_name: str, response: HttpJsonResponse, *, user_agent: str) -> CachedSecJson:
    cache_path, metadata_path = cache_paths(cache_dir, cache_name)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(response.raw_text, encoding="utf-8")
    metadata = {
        "source_url": response.url,
        "retrieved_at": response.retrieved_at,
        "sha256": response.sha256,
        "api_level": "Level 1",
        "source_type": "SEC_EDGAR_PUBLIC_API",
        "status_code": response.status_code,
        "user_agent_hash": hashlib.sha256(user_agent.strip().encode("utf-8")).hexdigest() if user_agent else "",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return CachedSecJson(
        payload=response.payload,
        url=response.url,
        cache_path=cache_path,
        metadata_path=metadata_path,
        sha256=response.sha256,
        retrieved_at=response.retrieved_at,
        cache_hit=False,
    )


def _read_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
