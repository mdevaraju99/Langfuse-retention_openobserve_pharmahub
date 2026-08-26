"""
Benchmark runner for retrieval and generation latency/capacity reporting.
"""
from __future__ import annotations

import json
import time
import csv
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Dict, List

import psutil

from .agentic_rag import complete_groq_chat
from .rag_pipeline import get_documents_list, get_rag_context


DEFAULT_QUERIES = [
    "What is the primary endpoint in the uploaded trial document?",
    "Summarize key safety findings and adverse events.",
    "What dosing schedule is described?",
    "Compare protocol objectives with reported outcomes.",
    "Which biomarkers are discussed and why?",
]


def _p95(values: List[float]) -> float:
    if not values:
        return 0.0
    arr = sorted(values)
    idx = int(round(0.95 * (len(arr) - 1)))
    return arr[idx]


def run_benchmark_suite(
    queries: List[str] | None = None,
    include_generation: bool = True,
    output_dir: str = "data/benchmarks",
) -> Dict:
    proc = psutil.Process()
    mem_before_mb = round(proc.memory_info().rss / (1024 * 1024), 2)
    mem_peak_mb = mem_before_mb

    q = [x.strip() for x in (queries or DEFAULT_QUERIES) if x.strip()]
    if not q:
        q = DEFAULT_QUERIES

    retrieval_ms: List[float] = []
    generation_ms: List[float] = []
    context_chars: List[int] = []
    samples: List[Dict] = []

    docs = get_documents_list()
    total_chunks = sum(int(d.get("chunk_count") or 0) for d in docs)

    for query in q:
        t0 = time.perf_counter()
        ctx = get_rag_context(query, top_k=15, max_docs=5)
        t1 = time.perf_counter()
        r_ms = (t1 - t0) * 1000
        retrieval_ms.append(r_ms)
        c_len = len(ctx or "")
        context_chars.append(c_len)
        mem_now_mb = round(proc.memory_info().rss / (1024 * 1024), 2)
        mem_peak_mb = max(mem_peak_mb, mem_now_mb)

        g_ms = 0.0
        if include_generation and c_len > 0:
            g0 = time.perf_counter()
            _ = complete_groq_chat(
                [
                    {"role": "system", "content": "Answer concisely from context only."},
                    {"role": "user", "content": f"CONTEXT:\n{ctx}\n\nQUESTION:\n{query}"},
                ],
                model=config.GROQ_MODEL_FAST,
            )
            g1 = time.perf_counter()
            g_ms = (g1 - g0) * 1000
            generation_ms.append(g_ms)

        samples.append(
            {
                "query": query,
                "retrieval_ms": round(r_ms, 2),
                "generation_ms": round(g_ms, 2),
                "context_chars": c_len,
            }
        )

    report = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "queries": len(q),
        "documents": len(docs),
        "total_chunks": total_chunks,
        "retrieval_avg_ms": round(mean(retrieval_ms) if retrieval_ms else 0.0, 2),
        "retrieval_p95_ms": round(_p95(retrieval_ms), 2),
        "generation_avg_ms": round(mean(generation_ms) if generation_ms else 0.0, 2),
        "generation_p95_ms": round(_p95(generation_ms), 2),
        "context_avg_chars": round(mean(context_chars) if context_chars else 0.0, 2),
        "memory_before_mb": mem_before_mb,
        "memory_peak_mb": round(mem_peak_mb, 2),
        "memory_delta_mb": round(mem_peak_mb - mem_before_mb, 2),
        "samples": samples,
    }

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"benchmark_{stamp}.json"
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    csv_file = out_dir / f"benchmark_{stamp}.csv"
    with csv_file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["query", "retrieval_ms", "generation_ms", "context_chars"]
        )
        writer.writeheader()
        for row in samples:
            writer.writerow(row)

    report["report_file"] = str(out_file)
    report["csv_file"] = str(csv_file)
    return report
