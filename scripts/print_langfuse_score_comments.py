"""Deprecated — use: python ops/cli.py print-scores --poc pharma-hub --trace-id <id>"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
poc = os.getenv("POC_ID", "pharma-hub")
trace_id = sys.argv[1] if len(sys.argv) > 1 else ""
if not trace_id:
    print("Usage: python ops/cli.py print-scores --poc pharma-hub --trace-id TRACE_ID")
    raise SystemExit(1)
raise SystemExit(
    subprocess.call(
        [
            sys.executable,
            str(ROOT / "ops" / "cli.py"),
            "print-scores",
            "--poc",
            poc,
            "--trace-id",
            trace_id,
        ],
        cwd=str(ROOT),
    )
)
