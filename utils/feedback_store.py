"""
Simple JSONL feedback storage for continuous improvement.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional


def _default_path() -> Path:
    return Path("data") / "feedback" / "rag_feedback.jsonl"


def append_feedback(
    question: str,
    answer: str,
    rating: str,
    comment: str = "",
    metadata: Optional[Dict] = None,
    path: Optional[str] = None,
) -> str:
    """
    rating: thumbs_up | thumbs_down
    """
    out_path = Path(path) if path else _default_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "answer": answer,
        "rating": rating,
        "comment": comment,
        "metadata": metadata or {},
    }
    with out_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    return str(out_path)
