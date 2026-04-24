#!/usr/bin/env python3
from __future__ import annotations

import runpy
from pathlib import Path

_CANONICAL_PATH = Path(__file__).resolve().parent / "tooling" / "patch_tool.py"

if not _CANONICAL_PATH.is_file():
    raise FileNotFoundError(f"Canonical patch tool not found: {_CANONICAL_PATH}")

runpy.run_path(str(_CANONICAL_PATH), run_name="__main__")
