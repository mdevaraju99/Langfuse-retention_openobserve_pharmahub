from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator, Optional

import config

_initialized = False
_trace_provider: Any = None
_log_provider: Any = None
_meter_provider: Any = None
_log_handler_attached = False
# Set when the collector is unreachable: keeps OTLP exporters from retrying
# every batch for the rest of the process (that floods the console).
_disabled = False

# Metric instruments (lazy)
_turn_counter: Any = None
_turn_duration: Any = None
_retrieval_duration: Any = None
_error_counter: Any = None
_histograms: dict[str, Any] = {}


def _normalize_basic_auth_header(token: str) -> Optional[str]:
    t = (token or "").strip()
    if not t:
        return None
    if t.lower().startswith("basic "):
        return t
    return f"Basic {t}"


def _otlp_headers(auth_header: str, stream: str) -> dict[str, str]:
    return {"Authorization": auth_header, "stream-name": stream}


def is_openobserve_enabled() -> bool:
    if _disabled:
        return False
    if not getattr(config, "ENABLE_OPENOBSERVE", False):
        return False
    return bool(_normalize_basic_auth_header(getattr(config, "OPENOBSERVE_AUTH_TOKEN", "")))


def _is_reachable(url: str, timeout: float = 2.0) -> bool:
    try:
        import requests

        return requests.get(f"{url}/healthz", timeout=timeout).status_code < 500
    except Exception:
        return False


def get_tracer(name: str = "pharma-hub"):
    if not is_openobserve_enabled():
        return None
    setup_openobserve()
    try:
        from opentelemetry import trace as otel_trace

        return otel_trace.get_tracer(name)
    except Exception:
        return None


def flush_openobserve() -> None:
    for provider in (_trace_provider, _log_provider, _meter_provider):
        if provider is None:
            continue
        try:
            provider.force_flush(timeout_millis=5000)
        except Exception:
            pass


def log_event(message: str, *, level: int = logging.INFO, attributes: Optional[dict[str, Any]] = None) -> None:
    """Emit a structured log line to OpenObserve (and console)."""
    if not is_openobserve_enabled():
        return
    setup_openobserve()
    logger = logging.getLogger("pharma-hub")
    payload = message if not attributes else f"{message} | {attributes}"
    try:
        logger.log(level, payload)
    except Exception:
        pass


def record_counter(name: str, value: float = 1.0, *, attributes: Optional[dict[str, Any]] = None) -> None:
    if not is_openobserve_enabled():
        return
    setup_openobserve()
    attrs = _norm_attrs(attributes)
    try:
        if name == "pharma.rag.turn.total" and _turn_counter is not None:
            _turn_counter.add(value, attributes=attrs)
        elif name == "pharma.rag.error.total" and _error_counter is not None:
            _error_counter.add(value, attributes=attrs)
    except Exception:
        pass


def record_histogram(name: str, value: float, *, attributes: Optional[dict[str, Any]] = None) -> None:
    if not is_openobserve_enabled():
        return
    setup_openobserve()
    inst = _instrument_for(name)
    if inst is None:
        return
    try:
        inst.record(value, attributes=_norm_attrs(attributes))
    except Exception:
        pass


def _instrument_for(name: str):
    if name == "pharma.rag.turn.duration_ms":
        return _turn_duration
    if name == "pharma.rag.retrieval.duration_ms":
        return _retrieval_duration
    inst = _histograms.get(name)
    if inst is None:
        try:
            from opentelemetry import metrics

            inst = metrics.get_meter("pharma-hub").create_histogram(name)
            _histograms[name] = inst
        except Exception:
            return None
    return inst


def _norm_attrs(attrs: Optional[dict[str, Any]]) -> dict[str, str | int | float | bool]:
    out: dict[str, str | int | float | bool] = {}
    if not attrs:
        return out
    for k, v in attrs.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            out[str(k)] = v
        else:
            out[str(k)] = str(v)[:500]
    return out


def mark_current_span_ok() -> None:
    """Set the active OpenTelemetry span status to OK (shows as OK in OpenObserve)."""
    try:
        from opentelemetry import trace as otel_trace
        from opentelemetry.trace import Status, StatusCode

        span = otel_trace.get_current_span()
        if span is not None and getattr(span, "is_recording", lambda: False)():
            span.set_status(Status(StatusCode.OK))
    except Exception:
        pass


def mark_current_span_error(message: str = "") -> None:
    """Set the active OpenTelemetry span status to ERROR (shows as ERROR in OpenObserve)."""
    try:
        from opentelemetry import trace as otel_trace
        from opentelemetry.trace import Status, StatusCode

        span = otel_trace.get_current_span()
        if span is not None and getattr(span, "is_recording", lambda: False)():
            span.set_status(Status(StatusCode.ERROR, (message or "")[:200]))
            if message:
                span.record_exception(RuntimeError(message[:500]))
    except Exception:
        pass


@contextmanager
def trace_span(
    name: str,
    *,
    attributes: Optional[dict[str, Any]] = None,
) -> Iterator[Any]:
    tracer = get_tracer("pharma-hub")
    if tracer is None:
        yield None
        return

    from opentelemetry.trace import Status, StatusCode

    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                if value is None:
                    continue
                try:
                    span.set_attribute(key, value)
                except Exception:
                    pass
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise


def setup_openobserve() -> None:
    global _initialized, _trace_provider, _log_provider, _meter_provider
    global _log_handler_attached, _disabled
    global _turn_counter, _turn_duration, _retrieval_duration, _error_counter

    if _initialized or _disabled:
        return

    if not getattr(config, "ENABLE_OPENOBSERVE", False):
        return

    auth_header = _normalize_basic_auth_header(getattr(config, "OPENOBSERVE_AUTH_TOKEN", ""))
    if not auth_header:
        print("[OpenObserve] ENABLE_OPENOBSERVE=true but OPENOBSERVE_AUTH_TOKEN is empty. Skipping.")
        return

    url = getattr(config, "OPENOBSERVE_URL", "http://localhost:5080").rstrip("/")
    org = getattr(config, "OPENOBSERVE_ORG", "default")
    trace_stream = getattr(config, "OPENOBSERVE_STREAM", "default")
    log_stream = getattr(config, "OPENOBSERVE_LOGS_STREAM", "pharma-hub-logs")
    metric_stream = getattr(config, "OPENOBSERVE_METRICS_STREAM", "pharma-hub-metrics")
    service_name = getattr(config, "OPENOBSERVE_SERVICE_NAME", "pharma-hub")
    poc_id = (os.getenv("POC_ID", "") or "").strip()[:200]

    if not _is_reachable(url):
        _disabled = True
        print(
            f"[OpenObserve] Not reachable at {url} — telemetry disabled for this run.\n"
            "             Start it with: .\\scripts\\start_openobserve_podman.ps1\n"
            "             (or set ENABLE_OPENOBSERVE=false in .env to silence this)"
        )
        return

    resource_attrs: dict[str, str] = {"service.name": service_name}
    if poc_id:
        resource_attrs["poc.id"] = poc_id

    try:
        from opentelemetry import metrics, trace
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.langchain import LangchainInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        from opentelemetry.metrics import set_meter_provider
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception as e:
        print(f"[OpenObserve] Missing OpenTelemetry packages? {e}. Skipping.")
        return

    resource = Resource.create(resource_attrs)
    headers_trace = _otlp_headers(auth_header, trace_stream)
    headers_logs = _otlp_headers(auth_header, log_stream)
    headers_metrics = _otlp_headers(auth_header, metric_stream)

    # --- Traces ---
    trace_exporter = OTLPSpanExporter(endpoint=f"{url}/api/{org}/v1/traces", headers=headers_trace)
    _trace_provider = TracerProvider(resource=resource)
    _trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(_trace_provider)

    # --- Logs ---
    log_exporter = OTLPLogExporter(endpoint=f"{url}/api/{org}/v1/logs", headers=headers_logs)
    _log_provider = LoggerProvider(resource=resource)
    _log_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
    set_logger_provider(_log_provider)

    if not _log_handler_attached:
        handler = LoggingHandler(level=logging.INFO, logger_provider=_log_provider)
        app_logger = logging.getLogger("pharma-hub")
        app_logger.addHandler(handler)
        app_logger.setLevel(logging.INFO)
        if not app_logger.handlers or all(h is handler for h in app_logger.handlers):
            app_logger.propagate = True
        _log_handler_attached = True

    # --- Metrics ---
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{url}/api/{org}/v1/metrics", headers=headers_metrics),
        export_interval_millis=30_000,
    )
    _meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    set_meter_provider(_meter_provider)

    meter = metrics.get_meter("pharma-hub")
    _turn_counter = meter.create_counter("pharma.rag.turn.total", description="RAG user turns")
    _turn_duration = meter.create_histogram("pharma.rag.turn.duration_ms", unit="ms")
    _retrieval_duration = meter.create_histogram("pharma.rag.retrieval.duration_ms", unit="ms")
    _error_counter = meter.create_counter("pharma.rag.error.total", description="RAG errors")

    try:
        LangchainInstrumentor().instrument()
    except Exception:
        pass

    try:
        RequestsInstrumentor().instrument(excluded_urls="localhost,127.0.0.1,::1")
    except Exception:
        pass

    _initialized = True
    log_event("openobserve.initialized", attributes={"service": service_name, "org": org})
