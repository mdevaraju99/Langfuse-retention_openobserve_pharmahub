"""Shared Langfuse SDK helpers used by all ops commands."""
from __future__ import annotations

from typing import Any, Optional

from ops.config_loader import PocConfig


def mask_secret(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return "(not set)"
    if len(s) <= 10:
        return "***"
    return f"{s[:8]}...{s[-4:]}"


def configured(cfg: PocConfig) -> bool:
    lf = cfg.langfuse
    return bool(lf.public_key and lf.secret_key and lf.host)


def get_client(cfg: PocConfig) -> Any:
    if not configured(cfg):
        raise RuntimeError(
            f"Langfuse not configured for POC '{cfg.poc_id}'. "
            "Set LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL in .env"
        )
    try:
        from langfuse import Langfuse
    except ImportError as e:
        raise RuntimeError("Install langfuse: pip install langfuse") from e

    return Langfuse(
        public_key=cfg.langfuse.public_key,
        secret_key=cfg.langfuse.secret_key,
        base_url=cfg.langfuse.host,
    )


def verify_credentials(cfg: PocConfig) -> tuple[bool, str]:
    if not configured(cfg):
        return False, "Missing LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, or LANGFUSE_BASE_URL"

    import base64

    import requests

    token = base64.b64encode(
        f"{cfg.langfuse.public_key}:{cfg.langfuse.secret_key}".encode()
    ).decode()
    try:
        r = requests.get(
            f"{cfg.langfuse.host}/api/public/projects",
            headers={"Authorization": f"Basic {token}"},
            timeout=10,
        )
    except requests.RequestException as e:
        return False, f"Cannot reach Langfuse at {cfg.langfuse.host}: {e}"

    if r.status_code == 200:
        return True, "Langfuse API keys accepted."
    if r.status_code == 401:
        return False, "Langfuse rejected API keys (401). Create new keys in the Langfuse UI."
    return False, f"Langfuse API returned HTTP {r.status_code}: {r.text[:200]}"


def seed_prompt(
    cfg: PocConfig,
    prompt_text: str,
    *,
    label: str = "production",
    config_meta: Optional[dict] = None,
) -> int:
    lf = get_client(cfg)
    result = lf.create_prompt(
        name=cfg.langfuse.prompt_rag,
        type="text",
        prompt=prompt_text,
        labels=[label] if label else [],
        config=config_meta or {"poc_id": cfg.poc_id},
    )
    lf.flush()
    version = getattr(result, "version", None)
    if version is None and isinstance(result, dict):
        version = result.get("version")
    return int(version or 0)


def send_test_trace(cfg: PocConfig) -> None:
    lf = get_client(cfg)
    tags = cfg.langfuse.tags or [f"product:{cfg.poc_id}"]
    with lf.start_as_current_observation(
        name="ops_connection_test",
        as_type="chain",
        input={"poc_id": cfg.poc_id, "test": True},
        metadata={"tags": tags},
    ):
        if hasattr(lf, "update_current_trace"):
            lf.update_current_trace(tags=tags)
        lf.update_current_span(output={"ok": True, "poc_id": cfg.poc_id})
    lf.flush()
