"""print-scores — print full Langfuse score comments for a trace."""
from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

from ops.config_loader import PocConfig


def run(cfg: PocConfig, trace_id: str) -> int:
    lf = cfg.langfuse
    if not lf.public_key or not lf.secret_key:
        print("Missing Langfuse API keys in .env")
        return 1

    token = base64.b64encode(f"{lf.public_key}:{lf.secret_key}".encode()).decode()
    url = f"{lf.host}/api/public/scores"
    params = {"traceId": trace_id.strip(), "limit": 100}

    r = requests.get(
        url,
        headers={"Authorization": f"Basic {token}"},
        params=params,
        timeout=30,
    )
    if r.status_code != 200:
        print(f"API error {r.status_code}: {r.text[:500]}")
        return 1

    payload = r.json()
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not rows:
        print(f"No scores for trace {trace_id}")
        return 0

    print(f"POC: {cfg.poc_id}  Trace: {trace_id}\n{'=' * 72}")
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


def run_with_env(trace_id: str, env_file: Optional[Path] = None) -> int:
    from ops.config_loader import load_poc_config
    import os

    poc = os.getenv("POC_ID", "pharma-hub")
    cfg = load_poc_config(poc, env_file=env_file)
    return run(cfg, trace_id)
