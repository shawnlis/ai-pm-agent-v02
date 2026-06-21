"""Explicit local state loading for autopm monitor artifacts.

The state store reads only caller-supplied files or directories. It does not
scan reports/outputs trees, fetch live data, connect to brokers, or inspect
private account paths.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any


RUN_MANIFEST_FILE = "autopm_run_manifest.json"
RANKINGS_FILE = "autopm_rankings.json"
RECOMMENDATIONS_FILE = "autopm_recommendations.json"
REBALANCE_FILE = "autopm_rebalance_proposal.json"
CLAIM_AUDIT_FILE = "autopm_claim_audit_summary.json"
OUTPUT_VALIDATION_FILE = "autopm_output_validation.json"
PAPER_STATE_FILE = "paper_portfolio_state.json"

KNOWN_JSON_FILES = (
    RUN_MANIFEST_FILE,
    RANKINGS_FILE,
    RECOMMENDATIONS_FILE,
    REBALANCE_FILE,
    CLAIM_AUDIT_FILE,
    OUTPUT_VALIDATION_FILE,
    PAPER_STATE_FILE,
)
DISALLOWED_PATH_TERMS = ("portfolio.csv", "ibkr", "broker", "client", "account", "statement")


class AutopmStateStoreError(ValueError):
    """Raised when explicit monitor state inputs fail closed."""


@dataclass(frozen=True)
class AutopmRunState:
    schema_version: str = ""
    run_id: str = ""
    as_of_date: str = ""
    mode: str = ""
    strategy: str = ""
    source_manifest_hash: str = ""
    rankings: tuple[dict[str, Any], ...] = ()
    recommendations: tuple[dict[str, Any], ...] = ()
    rebalance_rows: tuple[dict[str, Any], ...] = ()
    claim_audit: dict[str, Any] = field(default_factory=dict)
    output_validation: dict[str, Any] = field(default_factory=dict)
    paper_state: dict[str, Any] = field(default_factory=dict)
    loaded_files: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "as_of_date": self.as_of_date,
            "mode": self.mode,
            "strategy": self.strategy,
            "source_manifest_hash": self.source_manifest_hash,
            "rankings": list(self.rankings),
            "recommendations": list(self.recommendations),
            "rebalance_rows": list(self.rebalance_rows),
            "claim_audit": dict(self.claim_audit),
            "output_validation": dict(self.output_validation),
            "paper_state": dict(self.paper_state),
            "loaded_files": list(self.loaded_files),
        }


def assert_safe_monitor_path(path: str | Path) -> Path:
    candidate = Path(path)
    lowered = str(candidate).lower()
    if any(term in lowered for term in DISALLOWED_PATH_TERMS):
        raise AutopmStateStoreError("refusing broker/client/account/IBKR-looking monitor path")
    if not candidate.exists():
        raise AutopmStateStoreError(f"explicit monitor path does not exist: {candidate}")
    return candidate


def load_monitor_state(path: str | Path) -> AutopmRunState:
    """Load autopm monitor state from one explicit directory or JSON/CSV file."""

    explicit = assert_safe_monitor_path(path)
    payloads: dict[str, Any] = {}
    loaded: list[str] = []
    if explicit.is_file():
        payloads[explicit.name] = read_fixture_table_or_json(explicit)
        loaded.append(str(explicit))
    elif explicit.is_dir():
        # Deliberately no glob/rglob: only known artifact names under explicit directory.
        for name in KNOWN_JSON_FILES:
            child = explicit / name
            if child.exists() and child.is_file():
                payloads[name] = read_fixture_table_or_json(child)
                loaded.append(str(child))
    else:
        raise AutopmStateStoreError(f"unsupported explicit monitor path: {explicit}")
    return state_from_payloads(payloads, loaded_files=tuple(loaded))


def state_from_payloads(payloads: dict[str, Any], *, loaded_files: tuple[str, ...] = ()) -> AutopmRunState:
    manifest = _dict(payloads.get(RUN_MANIFEST_FILE))
    rankings = _ranking_rows(payloads.get(RANKINGS_FILE))
    recommendations = _recommendation_rows(payloads.get(RECOMMENDATIONS_FILE))
    rebalance_rows = _rebalance_rows(payloads.get(REBALANCE_FILE))
    paper_state = _dict(payloads.get(PAPER_STATE_FILE))
    return AutopmRunState(
        schema_version=_text(manifest.get("schema_version")),
        run_id=_text(manifest.get("run_id")),
        as_of_date=_text(manifest.get("as_of_date")),
        mode=_text(manifest.get("mode")),
        strategy=_text(manifest.get("strategy")),
        source_manifest_hash=_text(manifest.get("source_manifest_hash")),
        rankings=tuple(rankings),
        recommendations=tuple(recommendations),
        rebalance_rows=tuple(rebalance_rows),
        claim_audit=_dict(payloads.get(CLAIM_AUDIT_FILE)),
        output_validation=_dict(payloads.get(OUTPUT_VALIDATION_FILE)),
        paper_state=paper_state,
        loaded_files=loaded_files,
    )


def read_fixture_table_or_json(path: str | Path) -> Any:
    explicit = assert_safe_monitor_path(path)
    if explicit.suffix.lower() == ".json":
        payload = json.loads(explicit.read_text(encoding="utf-8"))
        if not isinstance(payload, (dict, list)):
            raise AutopmStateStoreError("JSON monitor artifact must be object or list")
        return payload
    if explicit.suffix.lower() == ".csv":
        with explicit.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    raise AutopmStateStoreError("monitor state supports only JSON/CSV fixture inputs")


def _ranking_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        return _list(value.get("rankings"))
    return []


def _recommendation_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        return _list(value.get("recommendations"))
    return []


def _rebalance_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        return _list(value.get("proposed_trades"))
    return []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()
