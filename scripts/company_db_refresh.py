"""Script wrapper for offline company DB refresh planning."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.cli.company_refresh import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
