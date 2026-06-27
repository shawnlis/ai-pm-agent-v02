from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.alpha_source_pack.loader import AlphaSourcePackValidationError, load_alpha_source_pack
from ai_pm_agent.alpha_source_pack.mapper import map_alpha_source_pack
from ai_pm_agent.alpha_source_pack.report_writer import render_review_report, write_review_report


FIXTURE_PACK = ROOT / "tests" / "fixtures" / "alpha_source_pack" / "2026-06-27"
SCRIPT = ROOT / "scripts" / "import_alpha_source_pack.py"
FORBIDDEN_REPORT_TERMS = [
    " buy ",
    " sell ",
    " hold ",
    " add ",
    " trim ",
    " action ",
    " target weight",
    " target_weight",
    " rebalance",
    " order ",
    " trade ",
]


def copy_pack(tmp_path: Path) -> Path:
    target = tmp_path / "pack"
    shutil.copytree(FIXTURE_PACK, target)
    return target


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def test_valid_pack_imports_review_first_queue(tmp_path: Path) -> None:
    pack = load_alpha_source_pack(FIXTURE_PACK)
    result = map_alpha_source_pack(pack)
    report = write_review_report(result, tmp_path)

    assert len(result.imported_signals) == 5
    assert len(result.imported_candidates) == 10
    assert result.boundary["mode"] == "review_first"
    assert result.boundary["autopm_enabled"] is False
    assert result.boundary["portfolio_context_used"] is False
    assert report.exists()
    assert "Alpha Source Pack Review Queue" in report.read_text(encoding="utf-8")


def test_draft_record_in_reviewed_signals_blocks_import(tmp_path: Path) -> None:
    pack_dir = copy_pack(tmp_path)
    path = pack_dir / "reviewed_signals.jsonl"
    rows = read_jsonl(path)
    rows[0]["review_status"] = "draft"
    write_jsonl(path, rows)

    with pytest.raises(AlphaSourcePackValidationError, match="unreviewed signal"):
        load_alpha_source_pack(pack_dir)


def test_missing_manifest_blocks_import(tmp_path: Path) -> None:
    pack_dir = copy_pack(tmp_path)
    (pack_dir / "manifest.json").unlink()

    with pytest.raises(AlphaSourcePackValidationError, match="missing required files"):
        load_alpha_source_pack(pack_dir)


def test_invalid_schema_blocks_import(tmp_path: Path) -> None:
    pack_dir = copy_pack(tmp_path)
    path = pack_dir / "reviewed_signals.jsonl"
    rows = read_jsonl(path)
    rows[0].pop("source_refs")
    write_jsonl(path, rows)

    with pytest.raises(AlphaSourcePackValidationError, match="missing required keys"):
        load_alpha_source_pack(pack_dir)


def test_unreviewed_record_blocks_import(tmp_path: Path) -> None:
    pack_dir = copy_pack(tmp_path)
    path = pack_dir / "reviewed_signals.jsonl"
    rows = read_jsonl(path)
    rows[0]["review_status"] = "pending"
    write_jsonl(path, rows)

    with pytest.raises(AlphaSourcePackValidationError, match="unreviewed signal"):
        load_alpha_source_pack(pack_dir)


def test_source_pack_path_parent_traversal_blocks(tmp_path: Path) -> None:
    copied = copy_pack(tmp_path)
    traversal_path = copied / ".." / copied.name

    with pytest.raises(AlphaSourcePackValidationError, match="parent traversal"):
        load_alpha_source_pack(traversal_path)


def test_source_pack_private_path_component_blocks(tmp_path: Path) -> None:
    private_root = tmp_path / "IBKR Positions"
    private_root.mkdir()
    copied = private_root / "pack"
    shutil.copytree(FIXTURE_PACK, copied)

    with pytest.raises(AlphaSourcePackValidationError, match="forbidden private-data path"):
        load_alpha_source_pack(copied)


def test_review_report_has_no_pm_action_language() -> None:
    result = map_alpha_source_pack(load_alpha_source_pack(FIXTURE_PACK))
    report = f" {render_review_report(result).lower()} "

    for term in FORBIDDEN_REPORT_TERMS:
        assert term not in report
    assert "Review-first output only" in render_review_report(result)
    assert "execution instruction" in render_review_report(result)


def test_no_autopm_mode_is_enabled() -> None:
    result = map_alpha_source_pack(load_alpha_source_pack(FIXTURE_PACK))

    assert result.boundary["mode"] == "review_first"
    assert result.boundary["autopm_enabled"] is False
    assert result.boundary["pm_decision_engine"] is False
    assert result.boundary["broker_connection"] is False


def test_import_does_not_require_portfolio_fields() -> None:
    result = map_alpha_source_pack(load_alpha_source_pack(FIXTURE_PACK))
    payload = result.as_dict()
    serialized = json.dumps(payload, sort_keys=True).lower()

    assert "portfolio_path" not in serialized
    assert "position_pct" not in serialized
    assert "target_weight" not in serialized
    assert result.boundary["portfolio_context_used"] is False


def test_source_provenance_is_preserved() -> None:
    result = map_alpha_source_pack(load_alpha_source_pack(FIXTURE_PACK))
    signal = result.imported_signals[0]

    assert signal.evidence_provenance
    provenance = signal.evidence_provenance[0]
    assert provenance.evidence_id in signal.source_refs
    assert provenance.source_name
    assert provenance.reliability in {"high", "medium", "low"}
    assert provenance.source_reference


def test_cli_writes_review_report(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source-pack",
            str(FIXTURE_PACK),
            "--out-dir",
            str(out_dir),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["boundary"]["mode"] == "review_first"
    assert payload["boundary"]["autopm_enabled"] is False
    assert payload["imported_signals"] == 5
    assert (out_dir / "alpha_source_pack_review.md").exists()


def test_cli_requires_explicit_source_pack() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "--source-pack" in completed.stderr
