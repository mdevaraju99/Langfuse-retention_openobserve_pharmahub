"""health-openobserve — verify OpenObserve OTLP config and send a test trace."""
from __future__ import annotations

from ops.openobserve_ops import configured, mask_secret, send_test_trace, verify_credentials

import config


def run(*, poc_id: str = "pharma-hub", send_trace: bool = True) -> int:
    print(f"OpenObserve health — POC: {poc_id}")
    print("-" * 55)
    print(f"  OPENOBSERVE_URL:          {getattr(config, 'OPENOBSERVE_URL', '') or '(not set)'}")
    print(f"  OPENOBSERVE_ORG:          {getattr(config, 'OPENOBSERVE_ORG', '') or '(not set)'}")
    print(f"  OPENOBSERVE_AUTH_TOKEN:   {mask_secret(getattr(config, 'OPENOBSERVE_AUTH_TOKEN', ''))}")
    print(f"  OPENOBSERVE_SERVICE_NAME: {getattr(config, 'OPENOBSERVE_SERVICE_NAME', '') or '(not set)'}")
    print(f"  OPENOBSERVE_STREAM:       {getattr(config, 'OPENOBSERVE_STREAM', '') or '(not set)'}")
    print(f"  configured:               {configured()}")
    print()

    ok, msg = verify_credentials()
    print(msg)
    if not ok:
        print()
        print("Fix:")
        print("  1. Run .\\scripts\\start_openobserve_podman.ps1")
        print("  2. Copy OPENOBSERVE_* values into .env")
        print("  3. Run: python ops/cli.py health-openobserve")
        return 1

    if not send_trace:
        return 0

    try:
        from utils.openobserve_setup import setup_openobserve

        setup_openobserve()
        send_test_trace(poc_id=poc_id)
        print("Sent test trace 'ops_connection_test'.")
        print("Sent test log 'ops.health.check' and sample metrics.")
        print("Check Traces / Logs / Metrics in the OpenObserve UI.")
    except Exception as exc:
        print(f"Test trace failed: {exc}")
        return 1

    return 0
