"""Script wrapper for AI infrastructure opportunity discovery v0.1."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_pm_agent.opportunity_discovery.runner import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
