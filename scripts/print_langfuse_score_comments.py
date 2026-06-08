"""
Print full Langfuse score comments for a trace (workaround when UI truncates comments).

Usage:
  python scripts/print_langfuse_score_comments.py
  python scripts/print_langfuse_score_comments.py db2d822a9674a17812dc149536192837

Reads LANGFUSE_* from project .env (same keys as the Streamlit app).
"""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DEFAULT_TRACE_ID = "db2d822a9674a17812dc149536192837"


def _auth_header() -> dict[str, str]:
    pk = (os.getenv("LANGFUSE_PUBLIC_KEY") or "").strip()
    sk = (os.getenv("LANGFUSE_SECRET_KEY") or "").strip()
    if not pk or not sk:
        raise SystemExit("Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in .env")
    token = base64.b64encode(f"{pk}:{sk}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def main() -> int:
    trace_id = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TRACE_ID).strip()
    host = (os.getenv("LANGFUSE_BASE_URL") or os.getenv("LANGFUSE_HOST") or "http://localhost:3000").rstrip("/")
    url = f"{host}/api/public/scores"
    params = {"traceId": trace_id, "limit": 100}

    r = requests.get(url, headers=_auth_header(), params=params, timeout=30)
    if r.status_code != 200:
        print(f"API error {r.status_code}: {r.text[:500]}", file=sys.stderr)
        return 1

    payload = r.json()
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not rows:
        print(f"No scores for trace {trace_id}")
        return 0

    print(f"Trace: {trace_id}\n{'=' * 72}")
    for i, row in enumerate(rows, 1):
        name = row.get("name", "?")
        value = row.get("value", row.get("stringValue", "?"))
        source = row.get("source", "?")
        comment = (row.get("comment") or "").strip()
        score_id = row.get("id", "")
        print(f"\n[{i}] {name}  value={value}  source={source}  id={score_id}")
        print("-" * 72)
        print(comment if comment else "(no comment)")
    print(f"\n{'=' * 72}\nTotal scores: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
