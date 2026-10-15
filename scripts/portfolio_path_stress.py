"""Run offline path research without the repository monolith shadowing its package."""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from ai_pm_agent.autopm.portfolio_path_stress import main

if __name__ == "__main__":
    raise SystemExit(main())
