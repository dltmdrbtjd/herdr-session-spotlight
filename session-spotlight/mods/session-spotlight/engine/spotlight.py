#!/usr/bin/env python3
"""Entry point the mod runs: python3 -B spotlight.py <command> ..."""

import os
import sys

sys.dont_write_bytecode = True  # never write __pycache__ into the mod folder (it would reload the mod)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from spotlight_engine.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
