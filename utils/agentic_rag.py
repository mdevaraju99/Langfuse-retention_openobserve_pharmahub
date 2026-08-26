"""
Lightweight agentic RAG: query rewrite, retrieval (caller-supplied), relevance grade, streamed answer.
Designed for Streamlit (no LangGraph dependency).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple
import time
import re

from groq import Groq
import httpx

import config
from utils.langfuse_trace import (
    flush_langfuse,
    get_langfuse_client,
    trim_trace_messages,
)
from utils.openobserve_setup import (
    flush_openobserve,
    mark_current_span_error,
    mark_current_span_ok,
    trace_span,
)


def _extract_usage(resp: Any) -> Dict[str, int]:
    """Read prompt/completion/total tokens from a Groq response (or chunk)."""
    try:
        usage = getattr(resp, "usage", None)
        if usage is None and isinstance(resp, dict):
            usage = resp.get("usage")
        if usage is None:
            return {}
        get = (lambda k: getattr(usage, k, None)) if not isinstance(usage, dict) else (lambda k: usage.get(k))
        prompt_t = int(get("prompt_tokens") or 0)
        completion_t = int(get("completion_tokens") or 0)
        total_t = int(get("total_tokens") or (prompt_t + completion_t))
        if not (prompt_t or completion_t or total_t):
            return {}
        return {"input": prompt_t, "output": completion_t, "total": total_t}
    except Exception:
        return {}


def _cost_details_from_usage(usage: Dict[str, int], model: str) -> Dict[str, float]:
    """
    Optional cost estimate. Disabled by default (free Groq tier).
    Enable by setting GROQ_PRICE_INPUT_PER_1M and GROQ_PRICE_OUTPUT_PER_1M in config/.env.
    """
    if not usage:
        return {}
    in_price = float(getattr(config, "GROQ_PRICE_INPUT_PER_1M", 0) or 0)
    out_price = float(getattr(config, "GROQ_PRICE_OUTPUT_PER_1M", 0) or 0)
    if in_price <= 0 and out_price <= 0:
        return {"input": 0.0, "output": 0.0, "total": 0.0}
    in_cost = (usage.get("input", 0) / 1_000_000.0) * in_price
    out_cost = (usage.get("output", 0) / 1_000_000.0) * out_price
    return {"input": round(in_cost, 8), "output": round(out_cost, 8), "total": round(in_cost + out_cost, 8)}


def _safe_obs_update(obs: Any, **kwargs: Any) -> None:
    """obs.update that tolerates SDK variants by retrying without unsupported keys."""
    try:
        obs.update(**kwargs)
        return
    except TypeError:
        for drop in ("cost_details", "usage_details", "metadata"):
            kwargs.pop(drop, None)
            try:
                obs.update(**kwargs)
                return
            except TypeError:
                continue
    except Exception:
        pass


def _client() -> Groq:
    return Groq(
        api_key=config.GROQ_API_KEY,
        http_client=httpx.Client(verify=config.get_ssl_verify()),
    )


def _primary_model() -> str:
    return getattr(config, "GROQ_MODEL_PRIMARY", None) or "openai/gpt-oss-120b"


def _fast_model() -> str:
    return getattr(config, "GROQ_MODEL_FAST", None) or "openai/gpt-oss-20b"


@dataclass
class AgentState:
    user_question: str
    rewritten_query: str = ""
    retrieval_plan: str = ""
    context: str = ""
    needs_clarification: bool = False
    clarification_question: str = ""
    relevance_pass: bool = False
    timings_ms: Dict[str, float] = field(default_factory=dict)
    trace: List[str] = field(default_factory=list)


def _is_ambiguous_heuristic(question: str) -> bool:
    q = (question or "").strip().lower()
    if len(q) < int(config.RAG_CLARIFIER_MIN_CHARS):
        return True
    vague = {"this", "that", "it", "those", "these", "thing", "stuff", "details", "explain this"}
    tokens = set(re.findall(r"[a-z]+", q))
    return len(tokens.intersection(vague)) >= 2


def ask_clarifying_question(user_question: str) -> str:
    """
    Generate one concise clarifying question when intent is ambiguous.
    """
    if not config.GROQ_API_KEY:
        return "Could you clarify your target drug/trial/document section so I can answer precisely?"
    c = _client()
    r = c.chat.completions.create(
        model=_fast_model(),
        temperature=0.1,
        max_tokens=80,
        messages=[
            {
                "role": "system",
                "content": "Ask ONE concise clarifying question for an ambiguous pharma query. No preamble.",
            },
            {"role": "user", "content": user_question},
        ],
    )
    return (r.choices[0].message.content or "").strip() or "Could you clarify your target drug/trial/document section?"


def create_retrieval_plan(user_question: str, rewritten_query: str) -> str:
    """
    Planner-agent output: short retrieval intent plan.
    """
    if not config.GROQ_API_KEY:
        return f"Use query `{rewritten_query or user_question}` and prioritize endpoint, safety, dosing, outcomes."
    c = _client()
    r = c.chat.completions.create(
        model=_fast_model(),
        temperature=0.1,
        max_tokens=120,
        messages=[
            {
                "role": "system",
                "content": "Create a 1-2 sentence retrieval plan for pharmaceutical RAG. Mention key evidence categories to fetch.",
            },
            {
                "role": "user",
                "content": f"QUESTION: {user_question}\nREWRITTEN_QUERY: {rewritten_query}",
            },
        ],
    )
    return (r.choices[0].message.content or "").strip()


def rewrite_query_for_retrieval(user_question: str) -> str:
    """Short model call to produce a retrieval-friendly query."""
    if not config.GROQ_API_KEY or not user_question.strip():
        return user_question.strip()

    c = _client()
    r = c.chat.completions.create(
        model=_fast_model(),
        temperature=0,
        max_tokens=120,
        messages=[
            {
                "role": "system",
                "content": (
                    "Rewrite the user's question into a concise search query for a biomedical document "
                    "retrieval system. Output ONLY the rewritten query, no quotes."
                ),
            },
            {"role": "user", "content": user_question},
        ],
    )
    out = (r.choices[0].message.content or "").strip()
    return out or user_question.strip()


def grade_context_relevance(question: str, context_prefix: str) -> bool:
    """Returns True if context likely supports an answer (cheap gate)."""
    if not config.GROQ_API_KEY:
        return True
    snippet = (context_prefix or "")[:6000]
    if not snippet.strip():
        return False

    c = _client()
    r = c.chat.completions.create(
        model=_fast_model(),
        temperature=0,
        max_tokens=5,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict relevance judge. Answer YES if the CONTEXT contains information "
                    "that could help answer the QUESTION. Otherwise answer NO. Reply with only YES or NO."
                ),
            },
            {
                "role": "user",
                "content": f"QUESTION:\n{question}\n\nCONTEXT:\n{snippet}",
            },
        ],
    )
    ans = (r.choices[0].message.content or "").strip().upper()
    return ans.startswith("Y")


def _groq_chat_complete_raw(
    messages: List[Dict[str, str]], model: Optional[str] = None
) -> Tuple[str, Dict[str, int]]:
    """Non-streaming Groq call. Returns (text, usage_dict)."""
    model = model or _primary_model()
    c = _client()
    r = c.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.35,
        max_tokens=2048,
        stream=False,
    )
    text = (r.choices[0].message.content or "").strip()
    return text, _extract_usage(r)


def stream_groq_chat(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    *,
    observation_name: Optional[str] = None,
    prompt: Optional[Any] = None,
) -> Generator[str, None, None]:
    """Token stream from Groq chat completions."""
    if not config.GROQ_API_KEY:
        yield "Set GROQ_API_KEY in .env to enable streaming."
        return

    model = model or _primary_model()
    obs_label = observation_name or "groq.chat.completion.stream"

    c = _client()
    base_kwargs = dict(
        model=model,
        messages=messages,
        temperature=0.35,
        max_tokens=2048,
        stream=True,
    )
    try:
        stream = c.chat.completions.create(
            **base_kwargs,
            stream_options={"include_usage": True},
        )
    except Exception:
        # Older Groq SDKs reject stream_options. Retry without it; usage will be
        # missing on streaming spans but the answer still streams normally.
        stream = c.chat.completions.create(**base_kwargs)
    buf: list[str] = []
    last_usage: Dict[str, int] = {}
    lf = get_langfuse_client()
    try:
        for chunk in stream:
            chunk_usage = _extract_usage(chunk)
            if chunk_usage:
                last_usage = chunk_usage
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            delta = choices[0].delta
            if delta and getattr(delta, "content", None):
                buf.append(delta.content)
                yield delta.content
    finally:
        if lf and buf:
            try:
                gen_kwargs: Dict[str, Any] = dict(
                    name=obs_label,
                    as_type="generation",
                    model=model,
                    input=trim_trace_messages(messages),
                    model_parameters={"temperature": 0.35, "max_tokens": 2048},
                )
                if prompt is not None:
                    gen_kwargs["prompt"] = prompt
                with lf.start_as_current_observation(**gen_kwargs) as obs:
                    _safe_obs_update(
                        obs,
                        output="".join(buf),
                        usage_details=last_usage or None,
                        cost_details=_cost_details_from_usage(last_usage, model) or None,
                    )
                    mark_current_span_ok()
                flush_langfuse()
            except Exception:
                mark_current_span_error("groq stream observation failed")
                pass


def complete_groq_chat(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    *,
    observation_name: Optional[str] = None,
    prompt: Optional[Any] = None,
) -> str:
    """Non-streaming completion (used when streaming UI is disabled)."""
    if not config.GROQ_API_KEY:
        return "Set GROQ_API_KEY in .env to enable answers."

    model = model or _primary_model()
    obs_label = observation_name or "groq.chat.completion"

    lf = get_langfuse_client()
    if not lf:
        out, _usage = _groq_chat_complete_raw(messages, model)
        return out

    try:
        gen_kwargs: Dict[str, Any] = dict(
            name=obs_label,
            as_type="generation",
            model=model,
            input=trim_trace_messages(messages),
            model_parameters={"temperature": 0.35, "max_tokens": 2048},
        )
        if prompt is not None:
            gen_kwargs["prompt"] = prompt
        with lf.start_as_current_observation(**gen_kwargs) as obs:
            try:
                out, usage = _groq_chat_complete_raw(messages, model)
                _safe_obs_update(
                    obs,
                    output=out,
                    usage_details=usage or None,
                    cost_details=_cost_details_from_usage(usage, model) or None,
                )
                mark_current_span_ok()
                return out
            except Exception as e:
                _safe_obs_update(obs, level="ERROR", status_message=str(e)[:2000])
                mark_current_span_error(str(e))
                raise
    finally:
        flush_langfuse()
        flush_openobserve()


def revise_answer_with_critic(
    question: str,
    context: str,
    draft_answer: str,
    issues: List[str],
    *,
    observation_name: Optional[str] = None,
) -> str:
    """
    Critic agent: revise answer to address validation issues while staying grounded.
    """
    issue_text = "\n".join([f"- {x}" for x in (issues or [])]) or "- Improve grounding/citations."
    messages = [
        {
            "role": "system",
            "content": (
                "You are a strict pharmaceutical answer critic. Revise the draft answer using ONLY the context "
                "for document-grounded claims. Include source citations like [file.pdf] for those claims. "
                "If the draft ends with a section titled **General context (not from your documents):**, "
                "keep that section unchanged at the end (it is intentional general orientation, not from the files). "
                "If context is insufficient for grounded claims, state it clearly in the grounded portion."
            ),
        },
        {
            "role": "user",
            "content": (
                f"QUESTION:\n{question}\n\nCONTEXT:\n{context}\n\nDRAFT_ANSWER:\n{draft_answer}\n\n"
                f"ISSUES_TO_FIX:\n{issue_text}"
            ),
        },
    ]
    return complete_groq_chat(
        messages,
        model=_primary_model(),
        observation_name=observation_name or "rag.critic.revision",
    )


def run_agentic_retrieval(
    user_question: str,
    retrieve: Callable[[str], str],
    trace: Optional[List[str]] = None,
) -> str:
    """
    Optional multi-step retrieval: rewrite -> retrieve -> if weak, retrieve with original.
    """
    t = trace if trace is not None else []

    rq = rewrite_query_for_retrieval(user_question)
    t.append(f"**Rewrite (retrieval):** {rq}")
    ctx = retrieve(rq)
    t.append(f"**Retrieved chars:** {len(ctx or '')}")

    if ctx and grade_context_relevance(user_question, ctx):
        t.append("**Relevance gate:** PASS")
        return ctx

    t.append("**Relevance gate:** retry with original question")
    ctx2 = retrieve(user_question)
    t.append(f"**Retrieved chars (retry):** {len(ctx2 or '')}")
    return ctx2 or ctx


def orchestrate_agentic_rag(
    user_question: str,
    retrieve: Callable[[str], str],
) -> Dict:
    """
    Structured multi-agent style orchestration with timings for observability.
    """
    with trace_span(
        "rag.agentic.orchestrate",
        attributes={"rag.question_chars": len(user_question or "")},
    ):
        return _orchestrate_agentic_rag_impl(user_question, retrieve)


def _orchestrate_agentic_rag_impl(
    user_question: str,
    retrieve: Callable[[str], str],
) -> Dict:
    state = AgentState(user_question=user_question)

    # Clarifier agent
    t0 = time.perf_counter()
    if _is_ambiguous_heuristic(user_question):
        state.needs_clarification = True
        state.clarification_question = ask_clarifying_question(user_question)
        state.trace.append("Clarifier: ambiguity detected.")
    else:
        state.trace.append("Clarifier: question clear.")
    state.timings_ms["clarifier"] = round((time.perf_counter() - t0) * 1000, 2)
    if state.needs_clarification:
        flush_openobserve()
        return {
            "rewritten_query": "",
            "retrieval_plan": "",
            "context": "",
            "trace": state.trace,
            "timings_ms": state.timings_ms,
            "needs_clarification": True,
            "clarification_question": state.clarification_question,
            "relevance_pass": False,
        }

    # Rewriter agent
    t1 = time.perf_counter()
    state.rewritten_query = rewrite_query_for_retrieval(user_question)
    state.timings_ms["rewrite"] = round((time.perf_counter() - t1) * 1000, 2)
    state.trace.append(f"Rewriter: `{state.rewritten_query}`")

    # Planner agent
    t2 = time.perf_counter()
    state.retrieval_plan = create_retrieval_plan(user_question, state.rewritten_query)
    state.timings_ms["planner"] = round((time.perf_counter() - t2) * 1000, 2)
    state.trace.append(f"Planner: {state.retrieval_plan}")

    # Retriever agent
    t3 = time.perf_counter()
    state.context = retrieve(state.rewritten_query)
    state.timings_ms["retrieve_primary"] = round((time.perf_counter() - t3) * 1000, 2)
    state.trace.append(f"Retriever(primary): chars={len(state.context or '')}")

    # Verifier gate
    t4 = time.perf_counter()
    state.relevance_pass = grade_context_relevance(user_question, state.context)
    state.timings_ms["relevance_gate"] = round((time.perf_counter() - t4) * 1000, 2)
    state.trace.append(f"Verifier(relevance): {'PASS' if state.relevance_pass else 'RETRY'}")

    if not state.relevance_pass:
        t5 = time.perf_counter()
        retry_context = retrieve(user_question)
        state.timings_ms["retrieve_retry"] = round((time.perf_counter() - t5) * 1000, 2)
        state.trace.append(f"Retriever(retry): chars={len(retry_context or '')}")
        if retry_context and len(retry_context) > len(state.context or ""):
            state.context = retry_context

    flush_openobserve()
    return {
        "rewritten_query": state.rewritten_query,
        "retrieval_plan": state.retrieval_plan,
        "context": state.context or "",
        "trace": state.trace,
        "timings_ms": state.timings_ms,
        "needs_clarification": False,
        "clarification_question": "",
        "relevance_pass": state.relevance_pass,
    }
