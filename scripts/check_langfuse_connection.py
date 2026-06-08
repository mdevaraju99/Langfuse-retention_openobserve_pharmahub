"""
Verify Langfuse .env keys against LANGFUSE_BASE_URL (same check the Streamlit app uses).

Usage:
  python scripts/check_langfuse_connection.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils.langfuse_trace import (  # noqa: E402
    _langfuse_configured,
    get_langfuse_client,
    verify_langfuse_credentials,
)
import config  # noqa: E402


def _mask(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "(not set)"
    if len(s) <= 10:
        return "***"
    return f"{s[:8]}...{s[-4:]}"


def main() -> int:
    print("Langfuse connection check")
    print("-" * 50)
    print(f"  ENABLE_LANGFUSE_TRACING: {config.ENABLE_LANGFUSE_TRACING}")
    print(f"  LANGFUSE_HOST:          {config.LANGFUSE_HOST or '(not set)'}")
    print(f"  LANGFUSE_PUBLIC_KEY:    {_mask(config.LANGFUSE_PUBLIC_KEY)}")
    print(f"  LANGFUSE_SECRET_KEY:    {_mask(config.LANGFUSE_SECRET_KEY)}")
    print(f"  configured:             {_langfuse_configured()}")
    print()

    ok, msg = verify_langfuse_credentials()
    print(msg)
    if not ok:
        print()
        print("Fix:")
        print("  1. Open LANGFUSE_BASE_URL in the browser (e.g. http://localhost:3000)")
        print("  2. Project > Settings > API Keys > Create new API key")
        print("  3. Copy pk-lf-... and sk-lf-... into .env (no extra spaces)")
        print("  4. Restart Streamlit and run this script again")
        return 1

    lf = get_langfuse_client()
    if lf is None:
        print("Client is None (is langfuse package installed?)")
        return 1

    with lf.start_as_current_observation(
        name="connection_test",
        as_type="chain",
        input={"test": True},
    ):
        lf.set_current_trace_io(input={"test": True}, output={"ok": True})
    lf.flush()
    print("Sent a test trace (connection_test). Check Traces in the Langfuse UI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
