"""openobserve-guide — how to use every OpenObserve feature with this POC."""
from __future__ import annotations

import config


def run() -> int:
    url = getattr(config, "OPENOBSERVE_URL", "http://localhost:5080").rstrip("/")
    org = getattr(config, "OPENOBSERVE_ORG", "default")
    traces = getattr(config, "OPENOBSERVE_STREAM", "default")
    logs = getattr(config, "OPENOBSERVE_LOGS_STREAM", "pharma-hub-logs")
    metrics = getattr(config, "OPENOBSERVE_METRICS_STREAM", "pharma-hub-metrics")
    service = getattr(config, "OPENOBSERVE_SERVICE_NAME", "pharma-hub")

    print("OpenObserve - Pharma Knowledge Hub feature guide")
    print("=" * 60)
    print(f"UI:      {url}/web/?org_identifier={org}")
    print(f"Service: {service}")
    print(f"Streams: traces={traces}  logs={logs}  metrics={metrics}")
    print()

    sections = [
        (
            "1) TRACES - latency and request flow",
            [
                f"Sidebar -> Traces -> stream '{traces}'",
                f"Filter: service_name = '{service}'",
                "Parent span: company_knowledge (one user question)",
                "Children: rag.agentic.orchestrate -> rag.neo4j.retrieve -> llm.groq.*",
                "Waterfall: click a trace row -> timeline view",
                "Errors: span_status = 'ERROR' OR filter operation_name != 'HEAD'",
            ],
        ),
        (
            "2) LOGS - app events and errors",
            [
                f"Sidebar -> Logs -> stream '{logs}'",
                f"Filter: service_name = '{service}'",
                "Examples: rag.turn.complete, rag.turn.error, rag.retrieval",
                "Match logs to a trace by timestamp",
            ],
        ),
        (
            "3) METRICS - counters and latency charts",
            [
                f"Sidebar -> Metrics -> stream '{metrics}'",
                "Metrics exported by this app:",
                "  - pharma.rag.turn.total",
                "  - pharma.rag.turn.duration_ms",
                "  - pharma.rag.retrieval.duration_ms",
                "  - pharma.rag.error.total",
                "Build charts: avg/p95 duration, error rate over time",
            ],
        ),
        (
            "4) DASHBOARDS - daily ops view",
            [
                "Sidebar -> Dashboards -> New dashboard",
                "Panel A (Metrics): avg pharma.rag.retrieval.duration_ms",
                "Panel B (Metrics): sum pharma.rag.error.total",
                "Panel C (Traces): count company_knowledge spans / 5m",
                "Panel D (Logs): ERROR logs last 1h",
            ],
        ),
        (
            "5) ALERTS - notify when RAG breaks",
            [
                "Sidebar -> Alerts -> New alert",
                "Example: pharma.rag.error.total > 0 in 5 minutes",
                "Example: p95(pharma.rag.retrieval.duration_ms) > 3000",
            ],
        ),
        (
            "6) DATA - streams and retention",
            [
                f"Sidebar -> Data -> streams: {traces}, {logs}, {metrics}",
                "Each OTLP signal uses its own stream-name header",
            ],
        ),
        (
            "7) NOT wired in this Streamlit POC",
            [
                "RUM (browser UX) - Streamlit front-end not instrumented",
                "Pipelines / Functions - create manually in OpenObserve if needed",
            ],
        ),
        (
            "8) Langfuse vs OpenObserve",
            [
                "OpenObserve: speed, errors, dashboards",
                "Langfuse: prompts, scores, evaluators, answer quality",
            ],
        ),
        (
            "9) Commands",
            [
                ".\\scripts\\start_openobserve_podman.ps1",
                "python ops/cli.py health-openobserve",
                "python ops/cli.py openobserve-guide",
            ],
        ),
    ]

    for title, bullets in sections:
        print(title)
        print("-" * len(title))
        for b in bullets:
            print(f"  - {b}")
        print()

    return 0
