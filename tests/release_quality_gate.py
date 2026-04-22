"""
Release quality gate for Agentic RAG v2.
Fails (exit code 1) if quality thresholds are not met.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, Optional

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import config


def _latest_json(prefix: str, folder: Path) -> Optional[Path]:
    files = sorted(folder.glob(f"{prefix}_*.json"))
    return files[-1] if files else None


def _load_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    bench_dir = BASE / "data" / "benchmarks"
    bench_file = _latest_json("benchmark", bench_dir)
    eval_file = _latest_json("case_eval", bench_dir)

    if not bench_file or not eval_file:
        print(
            "FAIL: Missing benchmark/case_eval reports. "
            "Run benchmark runner and case_study_eval first."
        )
        return 1

    bench = _load_json(bench_file)
    case_eval = _load_json(eval_file)

    retrieval_p95 = float(bench.get("retrieval_p95_ms", 0))
    case_pass_rate = float(case_eval.get("pass_rate", 0))
    min_case_pass = float(config.QUALITY_MIN_CASE_PASS_RATE)
    max_retrieval_p95 = float(config.QUALITY_MAX_RETRIEVAL_P95_MS)

    failures = []
    if case_pass_rate < min_case_pass:
        failures.append(
            f"case pass rate {case_pass_rate:.3f} < threshold {min_case_pass:.3f}"
        )
    if retrieval_p95 > max_retrieval_p95:
        failures.append(
            f"retrieval p95 {retrieval_p95:.2f}ms > threshold {max_retrieval_p95:.2f}ms"
        )

    result = {
        "benchmark_file": str(bench_file),
        "case_eval_file": str(eval_file),
        "retrieval_p95_ms": retrieval_p95,
        "case_pass_rate": case_pass_rate,
        "thresholds": {
            "QUALITY_MIN_CASE_PASS_RATE": min_case_pass,
            "QUALITY_MAX_RETRIEVAL_P95_MS": max_retrieval_p95,
        },
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
    }
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
