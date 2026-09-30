#!/usr/bin/env python3
"""Source-checkout launcher; implementation lives in the installed package."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from codebase_agent_setup.install import main

if __name__ == "__main__":
    raise SystemExit(main())
