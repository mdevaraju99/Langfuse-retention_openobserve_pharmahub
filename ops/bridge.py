"""
Call ops CLI from the backend (Streamlit) without duplicating integration code.

    from ops.bridge import run_ops
    run_ops("health", poc_id="pharma-hub")
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

OPS_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = OPS_ROOT.parent
OPS_CLI = OPS_ROOT / "cli.py"
DEFAULT_POC = os.getenv("POC_ID", "pharma-hub")


def run_ops(
    command: str,
    *,
    poc_id: Optional[str] = None,
    timeout: int = 120,
    capture: bool = False,
    **flags: Any,
) -> subprocess.CompletedProcess[str] | int:
    if not OPS_CLI.is_file():
        raise FileNotFoundError(f"Ops CLI not found: {OPS_CLI}")

    poc = (poc_id or DEFAULT_POC).strip()
    cmd: list[str] = [sys.executable, str(OPS_CLI), command]

    needs_poc = command not in ("list-pocs", "seed-evaluators")
    if needs_poc:
        cmd.extend(["--poc", poc])

    for key, value in flags.items():
        flag = f"--{key.replace('_', '-')}"
        if value is True:
            cmd.append(flag)
        elif value is False or value is None:
            continue
        else:
            cmd.extend([flag, str(value)])

    env = os.environ.copy()
    env.setdefault("POC_ID", poc)

    result = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=capture,
        text=True,
        timeout=timeout,
        check=False,
    )
    return result if capture else result.returncode
