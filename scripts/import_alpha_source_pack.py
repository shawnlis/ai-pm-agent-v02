"""CLI wrapper for the read-only Alpha Source Pack importer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.alpha_source_pack.loader import AlphaSourcePackValidationError, load_alpha_source_pack  # noqa: E402
from ai_pm_agent.alpha_source_pack.mapper import map_alpha_source_pack  # noqa: E402
from ai_pm_agent.alpha_source_pack.report_writer import write_review_report  # noqa: E402


def default_out_dir(source_pack: Path) -> Path:
    return ROOT / "outputs" / "alpha_source_pack_import" / source_pack.name


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import an Alpha Source Pack into a review-first queue.")
    parser.add_argument("--source-pack", type=Path, required=True, help="Explicit Alpha Source Pack directory.")
    parser.add_argument("--out-dir", type=Path, help="Output directory for alpha_source_pack_review.md.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        pack = load_alpha_source_pack(args.source_pack)
        result = map_alpha_source_pack(pack)
        out_dir = args.out_dir or default_out_dir(args.source_pack)
        report_path = write_review_report(result, out_dir)
    except AlphaSourcePackValidationError as exc:
        print(f"Alpha Source Pack import failed closed: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "report": str(report_path),
                "state_counts": result.state_counts,
                "imported_signals": len(result.imported_signals),
                "imported_candidates": len(result.imported_candidates),
                "boundary": result.boundary,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
