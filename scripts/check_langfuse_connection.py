"""Deprecated — use: python ops/cli.py health --poc pharma-hub"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
poc = os.getenv("POC_ID", "pharma-hub")
raise SystemExit(
    subprocess.call(
        [sys.executable, str(ROOT / "ops" / "cli.py"), "health", "--poc", poc],
        cwd=str(ROOT),
    )
)
