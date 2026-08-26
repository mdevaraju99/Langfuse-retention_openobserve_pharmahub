"""Record OpenObserve metrics for Pharma Knowledge Hub (no-op when disabled)."""
from __future__ import annotations

from typing import Optional

from utils.openobserve_setup import (
    flush_openobserve,
    record_counter,
    record_histogram,
    setup_openobserve,
)


def record_rag_retrieval_ms(duration_ms: float, *, context_chars: int = 0) -> None:
    setup_openobserve()
    record_histogram(
        "pharma.rag.retrieval.duration_ms",
        duration_ms,
        attributes={"context_chars": context_chars},
    )


def record_rag_turn(
    module: str,
    duration_ms: float,
    *,
    success: bool = True,
    context_chars: int = 0,
    agentic: bool = False,
) -> None:
    setup_openobserve()
    attrs = {
        "module": module,
        "success": success,
        "context_chars": context_chars,
        "agentic_rag": agentic,
    }
    record_counter("pharma.rag.turn.total", attributes=attrs)
    record_histogram("pharma.rag.turn.duration_ms", duration_ms, attributes=attrs)
    if not success:
        record_counter("pharma.rag.error.total", attributes={"module": module, "kind": "turn"})


def record_rag_error(module: str, error_type: str, message: Optional[str] = None) -> None:
    setup_openobserve()
    record_counter(
        "pharma.rag.error.total",
        attributes={
            "module": module,
            "kind": error_type,
            "message": (message or "")[:200],
        },
    )
    flush_openobserve()
