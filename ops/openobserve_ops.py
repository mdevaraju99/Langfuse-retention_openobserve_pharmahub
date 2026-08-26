"""Shared OpenObserve / OTLP helpers used by ops commands."""
from __future__ import annotations

import base64
import os
from typing import Tuple

import requests

import config
from utils.openobserve_setup import (
    flush_openobserve,
    get_tracer,
    is_openobserve_enabled,
    log_event,
    record_counter,
    record_histogram,
)


def mask_secret(value: str, visible: int = 4) -> str:
    v = (value or "").strip()
    if not v:
        return "(not set)"
    if len(v) <= visible * 2:
        return "*" * len(v)
    return f"{v[:visible]}...{v[-visible:]}"


def configured() -> bool:
    return is_openobserve_enabled()


def verify_credentials() -> Tuple[bool, str]:
    if not configured():
        return False, (
            "OpenObserve is off or incomplete. Set ENABLE_OPENOBSERVE=true and "
            "OPENOBSERVE_AUTH_TOKEN in .env."
        )

    url = getattr(config, "OPENOBSERVE_URL", "http://localhost:5080").rstrip("/")
    org = getattr(config, "OPENOBSERVE_ORG", "default")
    token = getattr(config, "OPENOBSERVE_AUTH_TOKEN", "")

    auth = token.strip()
    if auth and not auth.lower().startswith("basic "):
        auth = f"Basic {auth}"

    try:
        r = requests.get(
            f"{url}/healthz",
            timeout=10,
        )
        if r.status_code == 200:
            # Confirm OTLP auth by attempting a lightweight authenticated API call.
            org_check = requests.get(
                f"{url}/api/{org}/streams",
                headers={"Authorization": auth},
                timeout=10,
            )
            if org_check.status_code in (200, 404):
                return True, f"OpenObserve OK at {url} (org={org})"
            if org_check.status_code == 401:
                return False, "OpenObserve rejected credentials (401). Check OPENOBSERVE_AUTH_TOKEN."
            return True, f"OpenObserve reachable at {url} (auth probe HTTP {org_check.status_code})"
        return False, f"OpenObserve returned HTTP {r.status_code}: {r.text[:200]}"
    except Exception as exc:
        return False, f"Cannot reach OpenObserve at {url}: {exc}"


def send_test_trace(*, poc_id: str = "pharma-hub") -> None:
    tracer = get_tracer("ops.openobserve")
    if tracer is None:
        raise RuntimeError("OpenObserve tracer not initialized")

    with tracer.start_as_current_span("ops_connection_test") as span:
        span.set_attribute("poc.id", poc_id)
        span.set_attribute("test.source", "ops/cli.py health-openobserve")
        span.set_attribute("service.component", "openobserve-health")

    log_event("ops.health.check", attributes={"poc_id": poc_id, "signal": "logs"})
    record_counter("pharma.rag.turn.total", attributes={"module": "ops_test", "success": True})
    record_histogram("pharma.rag.retrieval.duration_ms", 42.0, attributes={"context_chars": 0})

    flush_openobserve()


def build_auth_token_from_credentials(email: str, password: str) -> str:
    raw = f"{email}:{password}".encode()
    return f"Basic {base64.b64encode(raw).decode()}"
