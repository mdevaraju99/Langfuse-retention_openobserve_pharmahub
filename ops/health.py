"""health — verify Langfuse keys and send a test trace for a POC."""
from __future__ import annotations

from ops.config_loader import PocConfig
from ops.langfuse_ops import configured, get_client, mask_secret, send_test_trace, verify_credentials


def run(cfg: PocConfig, *, send_trace: bool = True) -> int:
    lf = cfg.langfuse
    print(f"Langfuse health — POC: {cfg.poc_id} ({cfg.display_name})")
    print("-" * 55)
    print(f"  LANGFUSE_HOST:        {lf.host or '(not set)'}")
    print(f"  LANGFUSE_PUBLIC_KEY:  {mask_secret(lf.public_key)}")
    print(f"  LANGFUSE_SECRET_KEY:  {mask_secret(lf.secret_key)}")
    print(f"  configured:           {configured(cfg)}")
    print(f"  prompt:               {lf.prompt_rag} (label: {lf.prompt_label})")
    print(f"  tags:                 {', '.join(lf.tags) or '(none)'}")
    print()

    ok, msg = verify_credentials(cfg)
    print(msg)
    if not ok:
        print()
        print("Fix:")
        print("  1. Open LANGFUSE_BASE_URL in the browser")
        print("  2. Project > Settings > API Keys > Create new API key")
        print("  3. Copy keys into .env and run again")
        return 1

    if not send_trace:
        return 0

    try:
        send_test_trace(cfg)
        print(f"Sent test trace 'ops_connection_test' with tags: {cfg.langfuse.tags}")
        print("Check Traces in the Langfuse UI.")
    except Exception as e:
        print(f"Test trace failed: {e}")
        return 1

    if get_client(cfg) is None:
        return 1
    return 0
