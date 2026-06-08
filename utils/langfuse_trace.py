"""
Optional Langfuse observability (self-hosted or cloud).

Enabled when ENABLE_LANGFUSE is true (default) and LANGFUSE_PUBLIC_KEY,
LANGFUSE_SECRET_KEY, and LANGFUSE_BASE_URL (or LANGFUSE_HOST) are set.
"""
from __future__ import annotations

import getpass
import uuid
from contextlib import contextmanager, nullcontext
from typing import Any, Dict, Iterator, List, Optional

import config

_langfuse_client: Any = None
_auth_check_cache: Optional[bool] = None


def _langfuse_configured() -> bool:
    if not getattr(config, "ENABLE_LANGFUSE_TRACING", True):
        return False
    pk = getattr(config, "LANGFUSE_PUBLIC_KEY", "") or ""
    sk = getattr(config, "LANGFUSE_SECRET_KEY", "") or ""
    host = getattr(config, "LANGFUSE_HOST", "") or ""
    return bool(pk.strip() and sk.strip() and host.strip())


def get_langfuse_client():
    """Return a Langfuse client singleton, or None if disabled / not installed."""
    global _langfuse_client
    if not _langfuse_configured():
        return None
    if _langfuse_client is not None:
        return _langfuse_client
    try:
        from langfuse import Langfuse
    except ImportError:
        return None
    _langfuse_client = Langfuse(
        public_key=config.LANGFUSE_PUBLIC_KEY,
        secret_key=config.LANGFUSE_SECRET_KEY,
        base_url=config.LANGFUSE_HOST,
    )
    return _langfuse_client


def verify_langfuse_credentials() -> tuple[bool, str]:
    """
    Ping Langfuse REST API with project keys from config.
    Returns (ok, message). Caches the result for the process lifetime.
    """
    global _auth_check_cache
    if _auth_check_cache is not None:
        return _auth_check_cache, (
            "Langfuse API keys accepted."
            if _auth_check_cache
            else "Langfuse rejected API keys (401). Create new keys in the Langfuse UI for this host."
        )
    if not _langfuse_configured():
        _auth_check_cache = False
        return False, (
            "Langfuse tracing is off or incomplete. Set LANGFUSE_PUBLIC_KEY, "
            "LANGFUSE_SECRET_KEY, and LANGFUSE_BASE_URL in .env."
        )
    try:
        import base64
        import requests

        host = (config.LANGFUSE_HOST or "").rstrip("/")
        token = base64.b64encode(
            f"{config.LANGFUSE_PUBLIC_KEY}:{config.LANGFUSE_SECRET_KEY}".encode()
        ).decode()
        r = requests.get(
            f"{host}/api/public/projects",
            headers={"Authorization": f"Basic {token}"},
            timeout=10,
        )
        if r.status_code == 200:
            _auth_check_cache = True
            return True, f"Langfuse OK at {host}"
        if r.status_code == 401:
            _auth_check_cache = False
            return False, (
                f"Langfuse at {host} returned 401 Unauthorized. "
                "Keys in .env do not match this server - open that URL, Project Settings, "
                "API Keys, create a new key pair, paste into .env, restart Streamlit."
            )
        _auth_check_cache = False
        return False, f"Langfuse at {host} returned HTTP {r.status_code}: {r.text[:120]}"
    except Exception as exc:
        _auth_check_cache = False
        return False, f"Cannot reach Langfuse at {config.LANGFUSE_HOST}: {exc}"


def flush_langfuse() -> None:
    lf = get_langfuse_client()
    if lf is None:
        return
    try:
        lf.flush()
    except Exception:
        pass


def get_session_id(key: str) -> str:
    """
    Return a stable session id for the given namespace (e.g. 'chatbot', 'company_knowledge'),
    stored in Streamlit session_state so all turns in one user visit share the id.
    """
    try:
        import streamlit as st

        state_key = f"langfuse_session_id__{key}"
        sid = st.session_state.get(state_key)
        if not sid:
            sid = f"{key}-{uuid.uuid4().hex[:12]}"
            st.session_state[state_key] = sid
        return sid
    except Exception:
        return f"{key}-{uuid.uuid4().hex[:12]}"


def reset_session_id(key: str) -> None:
    """Drop a stored session id so the next turn starts a fresh Langfuse session."""
    try:
        import streamlit as st

        st.session_state.pop(f"langfuse_session_id__{key}", None)
    except Exception:
        return


_prompt_cache: Dict[str, Any] = {}


def get_managed_prompt(
    name: str,
    *,
    label: str = "production",
    fallback_text: str = "",
    variables: Optional[Dict[str, Any]] = None,
) -> tuple[str, Any]:
    """
    Fetch a Langfuse-managed prompt and return (compiled_text, prompt_object).

    - If Langfuse is not configured or fetch fails, returns (fallback_text, None)
      so the app keeps working with the hardcoded prompt.
    - `prompt_object` should be passed to Groq wrappers (`complete_groq_chat`,
      `stream_groq_chat`) so the trace's generation observation links back to
      the exact prompt version in Langfuse.
    """
    lf = get_langfuse_client()
    if lf is None:
        return fallback_text, None

    cache_key = f"{name}::{label}"
    cached = _prompt_cache.get(cache_key)
    prompt_obj = cached if cached is not None else None

    if prompt_obj is None:
        try:
            prompt_obj = lf.get_prompt(name, label=label)
            _prompt_cache[cache_key] = prompt_obj
        except Exception:
            return fallback_text, None

    try:
        text = prompt_obj.compile(**(variables or {}))
        if not text:
            return fallback_text, prompt_obj
        return text, prompt_obj
    except Exception:
        return fallback_text, prompt_obj


def clear_prompt_cache() -> None:
    """Drop the in-memory prompt cache so the next call re-fetches from Langfuse."""
    _prompt_cache.clear()


def get_user_id() -> str:
    """
    Best-effort user identifier (OS username). Returns 'demo_user' as fallback.
    Replace with real auth identity once available.
    """
    try:
        return getpass.getuser() or "demo_user"
    except Exception:
        return "demo_user"


@contextmanager
def apply_trace_context(
    lf: Any,
    *,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> Iterator[None]:
    """
    Attach session_id / user_id / tags to the currently active Langfuse trace.

    Use as a context manager *inside* a `lf.start_as_current_observation(...)` block:

        with lf.start_as_current_observation(name="chatbot", as_type="chain") as obs:
            with apply_trace_context(lf, session_id=sid, user_id=uid, tags=["chatbot"]):
                ...

    Implementation note:
      Langfuse v4 ships a `propagate_attributes` context manager, but in v4.5.x it
      does not reliably persist session.id/user.id at the trace level. Setting OTel
      span attributes directly (`session.id`, `user.id`, `langfuse.trace.tags`) is
      the supported wire format and works end-to-end. We also try `propagate_attributes`
      so child spans inherit values when supported by newer SDK builds.
    """
    if lf is None:
        yield
        return

    try:
        from opentelemetry import trace as otel_trace

        span = otel_trace.get_current_span()
        if span is not None and getattr(span, "is_recording", lambda: False)():
            if session_id:
                span.set_attribute("session.id", str(session_id)[:200])
            if user_id:
                span.set_attribute("user.id", str(user_id)[:200])
            if tags:
                clean_tags = [str(t)[:200] for t in tags if t]
                if clean_tags:
                    span.set_attribute("langfuse.trace.tags", clean_tags)
    except Exception:
        pass

    propagate = getattr(lf, "propagate_attributes", None)
    if propagate is not None:
        try:
            with propagate(session_id=session_id, user_id=user_id, tags=tags):
                yield
            return
        except Exception:
            pass

    update = getattr(lf, "update_current_trace", None)
    if update is not None:
        try:
            payload: Dict[str, Any] = {}
            if session_id:
                payload["session_id"] = session_id
            if user_id:
                payload["user_id"] = user_id
            if tags:
                payload["tags"] = tags
            if payload:
                update(**payload)
        except Exception:
            pass

    yield


def _coerce_score_value(value: Any) -> Any:
    """Langfuse accepts float for NUMERIC/BOOLEAN and str for CATEGORICAL/TEXT."""
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return str(value)


def score_current_trace(
    name: str,
    value: Any,
    *,
    data_type: Optional[str] = None,
    comment: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Attach a score to the *currently active* trace (call inside the
    `start_as_current_observation(...)` block). Silently no-ops when Langfuse
    is not configured.

    `data_type` ∈ {"NUMERIC","BOOLEAN","CATEGORICAL","TEXT"}; auto-picked when None.
    """
    lf = get_langfuse_client()
    if lf is None:
        return
    try:
        dt = data_type
        if dt is None:
            if isinstance(value, bool):
                dt = "BOOLEAN"
            elif isinstance(value, (int, float)):
                dt = "NUMERIC"
            else:
                dt = "CATEGORICAL"
        lf.score_current_trace(
            name=name,
            value=_coerce_score_value(value),
            data_type=dt,
            comment=comment,
            metadata=metadata,
        )
    except Exception:
        pass


def score_trace_by_id(
    trace_id: str,
    name: str,
    value: Any,
    *,
    data_type: Optional[str] = None,
    comment: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Attach a score to a specific trace_id that may already be closed
    (e.g. user clicks thumbs-up *after* the answer trace finished).
    """
    lf = get_langfuse_client()
    if lf is None or not trace_id:
        return
    try:
        dt = data_type
        if dt is None:
            if isinstance(value, bool):
                dt = "BOOLEAN"
            elif isinstance(value, (int, float)):
                dt = "NUMERIC"
            else:
                dt = "CATEGORICAL"
        lf.create_score(
            name=name,
            value=_coerce_score_value(value),
            trace_id=trace_id,
            data_type=dt,
            comment=comment,
            metadata=metadata,
        )
        flush_langfuse()
    except Exception:
        pass


def set_current_trace_io(
    *,
    question: str,
    answer: str = "",
    context_preview: Optional[str] = None,
    extra_input: Optional[Dict[str, Any]] = None,
    extra_output: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Mirror turn I/O on the Langfuse *trace* (Preview tab), not only on the chain span.

    SDK v3 often leaves trace-level input/output empty unless set explicitly.
    Call inside the active `start_as_current_observation` context, before flush.
    """
    lf = get_langfuse_client()
    if lf is None:
        return
    trace_input: Dict[str, Any] = {"question": question}
    if extra_input:
        trace_input.update(extra_input)
    trace_output: Dict[str, Any] = {"answer": (answer or "")[:6000]}
    if context_preview is not None:
        trace_output["context_preview"] = (context_preview or "")[:4000]
    if extra_output:
        trace_output.update(extra_output)
    try:
        lf.set_current_trace_io(input=trace_input, output=trace_output)
    except Exception:
        pass


def trim_trace_messages(
    messages: List[Dict[str, str]],
    max_total_chars: int = 16000,
) -> List[Dict[str, str]]:
    """Cap total serialized size for Langfuse inputs."""
    out: List[Dict[str, str]] = []
    used = 0
    for m in messages or []:
        role = str(m.get("role", ""))
        content = str(m.get("content", ""))
        if used + len(content) > max_total_chars:
            remain = max(0, max_total_chars - used)
            content = content[:remain] + ("…" if remain < len(content) else "")
        out.append({"role": role, "content": content})
        used += len(content)
        if used >= max_total_chars:
            break
    return out
