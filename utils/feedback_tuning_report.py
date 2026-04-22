"""
Offline feedback analysis job.
Generates a tuning report from stored feedback JSONL.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List


def load_feedback(path: str = "data/feedback/rag_feedback.jsonl") -> List[Dict]:
    p = Path(path)
    if not p.exists():
        return []
    rows: List[Dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def build_report(rows: List[Dict]) -> Dict:
    total = len(rows)
    up = sum(1 for r in rows if r.get("rating") == "thumbs_up")
    down = sum(1 for r in rows if r.get("rating") == "thumbs_down")
    comments = [str(r.get("comment", "")).strip().lower() for r in rows if str(r.get("comment", "")).strip()]

    keyword_counter = Counter()
    for c in comments:
        for kw in ["citation", "hallucination", "wrong", "missing", "unclear", "too long", "safety", "endpoint"]:
            if kw in c:
                keyword_counter[kw] += 1

    top_issues = [{"keyword": k, "count": v} for k, v in keyword_counter.most_common(10)]
    suggestions = []
    if keyword_counter.get("citation", 0) > 0:
        suggestions.append("Increase citation strictness in answer prompt and validation gate.")
    if keyword_counter.get("hallucination", 0) > 0 or keyword_counter.get("wrong", 0) > 0:
        suggestions.append("Raise confidence threshold and enforce abstain policy on low grounding.")
    if keyword_counter.get("missing", 0) > 0:
        suggestions.append("Increase retrieval breadth (top_k/max_docs) for broad questions.")
    if keyword_counter.get("unclear", 0) > 0:
        suggestions.append("Trigger clarifier more aggressively on ambiguous queries.")

    pass_rate = round(up / max(1, total), 3)
    return {
        "ts": datetime.utcnow().isoformat(),
        "total_feedback": total,
        "thumbs_up": up,
        "thumbs_down": down,
        "positive_rate": pass_rate,
        "top_issue_keywords": top_issues,
        "tuning_suggestions": suggestions,
    }


def write_report(report: Dict, out_dir: str = "data/feedback") -> str:
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    out = p / f"tuning_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return str(out)


if __name__ == "__main__":
    rows = load_feedback()
    rep = build_report(rows)
    path = write_report(rep)
    print(json.dumps({**rep, "report_file": path}, indent=2))
