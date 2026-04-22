"""
Lightweight agentic RAG: query rewrite, retrieval (caller-supplied), relevance grade, streamed answer.
Designed for Streamlit (no LangGraph dependency).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Generator, List, Optional
import time
import re

from groq import Groq

import config


def _client() -> Groq:
    return Groq(api_key=config.GROQ_API_KEY)


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
        model="llama-3.1-8b-instant",
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
        model="llama-3.1-8b-instant",
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
        model="llama-3.1-8b-instant",
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
        model="llama-3.1-8b-instant",
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


def stream_groq_chat(messages: List[Dict[str, str]], model: str = "llama-3.3-70b-versatile") -> Generator[str, None, None]:
    """Token stream from Groq chat completions."""
    if not config.GROQ_API_KEY:
        yield "Set GROQ_API_KEY in .env to enable streaming."
        return

    c = _client()
    stream = c.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.35,
        max_tokens=2048,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content


def complete_groq_chat(messages: List[Dict[str, str]], model: str = "llama-3.3-70b-versatile") -> str:
    """Non-streaming completion (used when streaming UI is disabled)."""
    if not config.GROQ_API_KEY:
        return "Set GROQ_API_KEY in .env to enable answers."

    c = _client()
    r = c.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.35,
        max_tokens=2048,
        stream=False,
    )
    return (r.choices[0].message.content or "").strip()


def revise_answer_with_critic(
    question: str,
    context: str,
    draft_answer: str,
    issues: List[str],
) -> str:
    """
    Critic agent: revise answer to address validation issues while staying grounded.
    """
    issue_text = "\n".join([f"- {x}" for x in (issues or [])]) or "- Improve grounding/citations."
    messages = [
        {
            "role": "system",
            "content": (
                "You are a strict pharmaceutical answer critic. Revise the draft answer using ONLY the context. "
                "Include source citations like [file.pdf] for factual claims. If context is insufficient, state it clearly."
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
    return complete_groq_chat(messages, model="llama-3.3-70b-versatile")


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
