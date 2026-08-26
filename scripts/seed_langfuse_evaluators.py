"""Deprecated — use: python ops/cli.py seed-evaluators"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
raise SystemExit(
    subprocess.call(
        [sys.executable, str(ROOT / "ops" / "cli.py"), "seed-evaluators"],
        cwd=str(ROOT),
    )
)
