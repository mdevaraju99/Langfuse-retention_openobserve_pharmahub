"""
Lightweight regression evaluator for case-study prompts.
Usage:
    python tests/case_study_eval.py
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from utils.rag_pipeline import get_rag_context
import config


def _load_cases(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _score_case(question: str, rules):
    ctx = get_rag_context(question, top_k=15, max_docs=5) or ""
    low = ctx.lower()
    hits = 0
    for term in rules:
        if term.lower() in low:
            hits += 1
    ratio = hits / max(1, len(rules))
    return {
        "context_chars": len(ctx),
        "rule_hits": hits,
        "rule_total": len(rules),
        "hit_ratio": round(ratio, 3),
    }


def main():
    data_file = BASE / "data" / "case_study_eval_set.json"
    cases = _load_cases(data_file)

    rows = []
    for case in cases:
        res = _score_case(case["question"], case.get("must_include_any", []))
        rows.append({"id": case["id"], **res})

    passed = sum(1 for r in rows if r["hit_ratio"] >= 0.4)
    summary = {
        "cases": len(rows),
        "passed": passed,
        "pass_rate": round(passed / max(1, len(rows)), 3),
        "rows": rows,
    }
    out_dir = BASE / "data" / "benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"case_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    summary["report_file"] = str(out_file)
    summary["quality_threshold_pass_rate"] = float(config.QUALITY_MIN_CASE_PASS_RATE)
    out_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
