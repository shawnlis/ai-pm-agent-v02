from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.autopm.output_validator import ValidationStatus, validate_output_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate an autopm output directory.")
    parser.add_argument("--run-dir", required=True, help="Autopm run output directory to validate.")
    parser.add_argument("--strict", action="store_true", help="Require strict claim audit pass for VALID output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = validate_output_dir(args.run_dir, strict=args.strict, write_artifacts=True)
    print(result.status.value)
    return 1 if result.status == ValidationStatus.INVALID else 0


if __name__ == "__main__":
    raise SystemExit(main())
