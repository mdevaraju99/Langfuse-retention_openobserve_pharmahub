"""
Company Knowledge Page (Multi-Document RAG with Neo4j)
Enhanced: streaming answers, agentic retrieval, capacity readout.
"""
import re
import time
from contextlib import nullcontext

import streamlit as st
import pandas as pd

import config
from utils.agentic_rag import (
    complete_groq_chat,
    orchestrate_agentic_rag,
    revise_answer_with_critic,
    stream_groq_chat,
)
from utils.answer_validator import validate_answer
from utils.feedback_store import append_feedback
from utils.rag_pipeline import (
    check_neo4j_connection,
    ingest_document,
    ingest_documents_batch,
    get_rag_context,
    get_documents_list,
    get_document_media_assets,
    delete_document,
    clear_all_documents,
)
from utils.spellcheck_util import suggest_for_text
from utils.langfuse_trace import (
    apply_trace_context,
    flush_langfuse,
    get_langfuse_client,
    get_managed_prompt,
    get_session_id,
    get_user_id,
    reset_session_id,
    score_current_trace,
    score_trace_by_id,
    set_current_trace_io,
)
from utils.openobserve_metrics import record_rag_error, record_rag_turn
from utils.openobserve_setup import (
    flush_openobserve,
    log_event,
    mark_current_span_error,
    mark_current_span_ok,
)


RAG_SYSTEM_PROMPT = """You are an expert pharmaceutical knowledge assistant with deep expertise in clinical trials, drug mechanisms, and regulatory affairs. You are analyzing multiple documents simultaneously.

INSTRUCTIONS:
1. For anything stated about the **uploaded documents**, use ONLY the provided context. Cite every such fact with [document_name.pdf]. Do not invent trial results, dosing, or product claims.
2. Use rich markdown: headers (##, ###), bullets, **bold**, tables where helpful.
3. For COMPARISON questions: use a markdown table and label sources per row.
4. For SAFETY questions: separate severity levels clearly.
5. End with a short **Conclusion** section.

WHEN THE DOCUMENTS DO NOT ANSWER THE QUESTION (e.g. background or definition missing in context):
6. Say clearly in the main answer that the specific detail is **not** in the provided documents (you may note what IS in the files if relevant).
7. Immediately after, add a section titled exactly **General context (not from your documents):** followed by **at most two short sentences** of widely accepted pharmaceutical/clinical orientation related to the user's question. No lists. No product-specific claims. This is general knowledge only, not sourced from the uploads.
"""


# Tiny follow-up when we skip the main RAG call (no retrieved text) or withhold a grounded answer.
_GENERAL_ORIENTATION_SYSTEM = (
    "You assist pharmaceutical users. The uploaded documents did not supply retrieved text, "
    "or the app could not ground an answer. Output ONLY markdown: start with the exact line "
    "**General context (not from your documents):** then one blank line, then at most 2 short sentences "
    "of accurate general pharmaceutical/clinical background related to the user's question. "
    "No bullet lists. No specific product or trial claims. If the question is unrelated to medicine/pharma, "
    "output one sentence saying general clinical context is not applicable."
)


def _general_orientation_tail(user_question: str) -> str:
    if not config.GROQ_API_KEY or not (user_question or "").strip():
        return ""
    try:
        tail = complete_groq_chat(
            [
                {"role": "system", "content": _GENERAL_ORIENTATION_SYSTEM},
                {"role": "user", "content": user_question.strip()},
            ],
            model=config.GROQ_MODEL_FAST,
            observation_name="llm.groq.orientation_tail",
        ).strip()
        return f"\n\n{tail}" if tail else ""
    except Exception:
        return ""


_GENERAL_CONTEXT_HEADING = re.compile(
    r"\*\*General context \(not from your documents\):\*\*",
    re.IGNORECASE | re.MULTILINE,
)


def _push_validation_scores(vd: dict, stage: str) -> None:
    """Send confidence / grounded_ratio / citation_count / decision as Langfuse scores."""
    try:
        score_current_trace(
            "confidence",
            int(vd.get("confidence", 0)),
            data_type="NUMERIC",
            comment=f"stage={stage}",
        )
        score_current_trace(
            "grounded_ratio",
            float(vd.get("grounded_ratio", 0.0)),
            data_type="NUMERIC",
            comment=f"stage={stage}",
        )
        score_current_trace(
            "citation_count",
            int(vd.get("citation_count", 0)),
            data_type="NUMERIC",
            comment=f"stage={stage}",
        )
        score_current_trace(
            "decision",
            str(vd.get("decision", "warn")),
            data_type="CATEGORICAL",
            comment=f"stage={stage}",
        )
    except Exception:
        pass


def _grounded_slice_for_validation(answer: str) -> str:
    """Score only the document-grounded portion; ignore the general-knowledge tail."""
    if not answer:
        return ""
    m = _GENERAL_CONTEXT_HEADING.search(answer)
    if m:
        return answer[: m.start()].strip()
    return answer.strip()


def _render_rag_quality_panel() -> None:
    """Metrics, trace, validation notes, and thumbs — collapsed under one expander."""
    ptrace = st.session_state.get("rag_panel_trace") or []
    pval = st.session_state.get("rag_panel_validation")
    if not ptrace and pval is None:
        return

    with st.expander("Agentic trace (retrieval)", expanded=False):
        if pval is not None:
            m1, m2, m3 = st.columns(3)
            m1.metric("Confidence", f"{pval['confidence']}%")
            m2.metric("Citations", str(pval["citation_count"]))
            m3.metric("Grounded ratio", f"{int(pval['grounded_ratio'] * 100)}%")
            if pval.get("decision") == "warn":
                st.info("Partial grounding detected. Verify critical claims against source docs.")
            issues = pval.get("issues") or []
            if issues:
                st.markdown("**Validation notes**")
                st.markdown("\n".join([f"- {x}" for x in issues]))
            st.markdown("---")
        if ptrace:
            st.markdown("**Retrieval trace**")
            st.markdown("\n\n".join(ptrace))
            st.markdown("---")
        st.caption("Feedback (optional)")
        feedback_comment = st.text_input(
            "Feedback note (optional)",
            key="rag_feedback_comment",
            placeholder="What was good or what needs correction?",
            label_visibility="collapsed",
        )
        u1, u2 = st.columns(2)
        with u1:
            up_clicked = st.button("👍 Save +1", key="rag_fb_up", use_container_width=True, type="secondary")
        with u2:
            down_clicked = st.button("👎 Save -1", key="rag_fb_down", use_container_width=True, type="secondary")
        if up_clicked or down_clicked:
            ex = st.session_state.get("last_rag_exchange", {})
            if ex:
                rating = "thumbs_up" if up_clicked else "thumbs_down"
                target = append_feedback(
                    question=ex.get("question", ""),
                    answer=ex.get("answer", ""),
                    rating=rating,
                    comment=feedback_comment,
                    metadata={
                        "validation": ex.get("validation", {}),
                        "context_chars": ex.get("context_chars", 0),
                    },
                )
                trace_id = ex.get("trace_id")
                if trace_id:
                    score_trace_by_id(
                        trace_id,
                        name="user_feedback",
                        value=1.0 if up_clicked else 0.0,
                        data_type="BOOLEAN",
                        comment=feedback_comment or rating,
                        metadata={"rating": rating},
                    )
                st.success(
                    f"Saved feedback to {target}"
                    + (" and Langfuse" if trace_id else "")
                )
            else:
                st.info("No response yet to save feedback for.")


def show():
    st.markdown(
        '<h2 class="gradient-header">🏢 Company Knowledge (Agentic RAG)</h2>',
        unsafe_allow_html=True,
    )
    st.markdown(
        "Upload pharma documents and ask grounded questions across them. "
        "Answers use **Agentic RAG** with source-aware retrieval. "
        "If the PDFs do not contain what you asked for, you still get a short "
        "**General context (not from your documents)** block (at most two sentences) for orientation."
    )

    docs = get_documents_list()

    with st.sidebar:
        st.markdown("### ⚙️ RAG / UX")
        use_stream = st.checkbox(
            "Stream answers (token-by-token)",
            value=bool(config.ENABLE_STREAMING_UI),
            help="Uses Groq streaming for a ChatGPT-like feel.",
        )
        use_agentic = st.checkbox(
            "Agentic RAG (rewrite → retrieve → relevance gate)",
            value=bool(config.ENABLE_AGENTIC_RAG_DEFAULT),
            help="Adds small extra LLM steps before answering to improve retrieval quality.",
        )

        st.markdown("---")
        st.markdown("### 📂 Document Upload")
        neo_ok, neo_msg = check_neo4j_connection()
        if neo_ok:
            st.caption("Neo4j status: connected")
        else:
            st.error(
                "Neo4j status: not connected. Document processing is disabled until Neo4j is running."
            )
            st.caption(neo_msg)

        uploaded_files = st.file_uploader(
            "Upload PDF Documents",
            type=["pdf"],
            accept_multiple_files=True,
            help="PDFs only. Tables are captured as text/markdown blocks when possible (PyMuPDF).",
        )

        if uploaded_files and st.button(
            "📥 Process Documents",
            use_container_width=True,
            disabled=not neo_ok,
        ):
            with st.spinner(
                f"Processing {len(uploaded_files)} document(s)... This may take 30–120 seconds."
            ):
                if len(uploaded_files) == 1:
                    success, message = ingest_document(uploaded_files[0], uploaded_files[0].name)
                else:
                    filenames = [f.name for f in uploaded_files]
                    success, message = ingest_documents_batch(uploaded_files, filenames)

                if success:
                    st.success(message)
                else:
                    st.error(message)

        st.markdown("---")
        st.markdown("### 📚 Document Library")

        docs = get_documents_list()

        if docs:
            st.info(f"**Total Documents:** {len(docs)}")

            for idx, doc in enumerate(docs):
                with st.expander(f"📄 {doc.get('filename', 'Unknown')}"):
                    st.write(f"**Uploaded:** {doc.get('upload_date', 'N/A')}")
                    if st.checkbox("Show extracted previews", value=False, key=f"media_preview_{idx}"):
                        media = get_document_media_assets(doc.get("filename", ""))
                        if media:
                            trows = media.get("tables", [])[: int(config.RAG_MAX_MEDIA_TABLE_PREVIEWS)]
                            imgs = media.get("images", [])[: int(config.RAG_MAX_MEDIA_IMAGES)]
                            formulas = media.get("formula_snippets", [])[: int(config.RAG_MAX_MEDIA_SNIPPETS)]
                            charts = media.get("chart_snippets", [])[: int(config.RAG_MAX_MEDIA_SNIPPETS)]
                            st.caption(
                                f"Tables: {len(trows)} | Images: {len(imgs)} | "
                                f"Formula snippets: {len(formulas)} | Chart snippets: {len(charts)}"
                            )
                            if trows:
                                st.markdown("**Table previews**")
                                for t_i, t in enumerate(trows[:2], start=1):
                                    st.caption(f"Table {t_i} (page {t.get('page', '-')})")
                                    st.markdown(t.get("markdown", ""))
                            if imgs:
                                st.image(imgs[0].get("path", ""), caption=f"Preview image (page {imgs[0].get('page', '-')})")
                        else:
                            st.caption("No extracted previews available yet.")

                    if st.button("🗑️ Delete", key=f"del_{idx}", use_container_width=True):
                        success, msg = delete_document(doc["filename"])
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

            st.markdown("---")

            if st.button("🗑️ Clear All Documents", use_container_width=True, type="secondary"):
                if st.session_state.get("confirm_clear", False):
                    success, msg = clear_all_documents()
                    if success:
                        st.success(msg)
                        st.session_state.confirm_clear = False
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.session_state.confirm_clear = True
                    st.warning("⚠️ Click again to confirm deletion of ALL documents")
        else:
            st.info("No documents uploaded yet. Upload PDFs above to get started!")

    st.markdown("---")

    if not docs:
        st.info("👈 Please upload documents in the sidebar to start chatting.")
        st.markdown("This module is built for **Agentic RAG over uploaded pharmaceutical documents**.")
        return

    if "rag_chat_history" not in st.session_state:
        st.session_state.rag_chat_history = []

    for message in st.session_state.rag_chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Ask questions across all your documents..."):
        st.session_state.rag_chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        def _retrieve(q: str) -> str:
            return get_rag_context(q, top_k=15, max_docs=5)

        with st.chat_message("assistant"):
            try:
                trace: list[str] = []
                context = ""
                validation = None
                if not config.GROQ_API_KEY:
                    answer = (
                        "⚠️ Set **GROQ_API_KEY** in your `.env` file to generate answers. "
                        "Retrieval still works locally, but the model needs a key."
                    )
                    st.warning(answer)
                    st.session_state.rag_panel_trace = []
                    st.session_state.rag_panel_validation = None
                else:
                    # One Langfuse trace per turn: chain → nested retrieve + LLM (clearer than separate top-level rows).
                    lf = get_langfuse_client()
                    kb_session_id = get_session_id("company_knowledge")
                    user_id = get_user_id()
                    chain_started = time.perf_counter()
                    turn_ok = True
                    chain_cm = (
                        lf.start_as_current_observation(
                            name="company_knowledge",
                            as_type="chain",
                            input={
                                "question": prompt,
                                "agentic_rag": use_agentic,
                                "stream_answers": use_stream,
                            },
                        )
                        if lf
                        else nullcontext()
                    )
                    answer = ""
                    captured_trace_id: str | None = None
                    trace_ctx = apply_trace_context(
                        lf,
                        session_id=kb_session_id,
                        user_id=user_id,
                        tags=["company_knowledge"],
                    )
                    # chain_cm first so the chain span is the currently active OTel
                    # span when apply_trace_context() sets session.id / user.id on it.
                    with chain_cm as chain_obs, trace_ctx:
                        try:
                            captured_trace_id = getattr(chain_obs, "trace_id", None) if chain_obs is not None else None
                        except Exception:
                            captured_trace_id = None
                        try:
                            if use_agentic:
                                orchestrated = orchestrate_agentic_rag(prompt, _retrieve)
                                if orchestrated.get("needs_clarification"):
                                    clarify_q = orchestrated.get(
                                        "clarification_question",
                                        "Could you clarify your question with a specific drug, endpoint, or document section?",
                                    )
                                    trace.extend(orchestrated.get("trace", []))
                                    trace.append("Clarifier requested more detail before retrieval.")
                                    answer = f"❓ {clarify_q}"
                                    st.info("Clarification requested before answering.")
                                    st.markdown(answer)
                                    st.session_state.rag_panel_trace = list(trace)
                                    st.session_state.rag_panel_validation = None
                                    st.session_state.rag_chat_history.append({"role": "assistant", "content": answer})
                                    st.session_state.last_rag_exchange = {
                                        "question": prompt,
                                        "answer": answer,
                                        "validation": {},
                                        "context_chars": 0,
                                        "trace_id": captured_trace_id,
                                    }
                                    return
                                context = orchestrated.get("context", "")
                                trace.extend(orchestrated.get("trace", []))
                                tms = orchestrated.get("timings_ms", {})
                                if tms:
                                    trace.append(
                                        "Timings (ms): " + ", ".join([f"{k}={v}" for k, v in tms.items()])
                                    )
                            else:
                                trace.append("**Agentic RAG:** disabled")
                                context = _retrieve(prompt)

                            if not context:
                                st.warning("No relevant information found in the documents.")
                                answer = (
                                    "I couldn't find relevant information in the uploaded documents "
                                    "to answer your question."
                                )
                                answer += _general_orientation_tail(prompt)
                                st.markdown(answer)
                            else:
                                system_text, prompt_obj = get_managed_prompt(
                                    "pharma/rag-system",
                                    label="production",
                                    fallback_text=RAG_SYSTEM_PROMPT,
                                )
                                messages = [
                                    {"role": "system", "content": system_text},
                                    {
                                        "role": "user",
                                        "content": f"CONTEXT FROM DOCUMENTS:\n{context}\n\nQUESTION:\n{prompt}",
                                    },
                                ]

                                if use_stream:
                                    pieces: list[str] = []

                                    def _gen():
                                        for ch in stream_groq_chat(
                                            messages,
                                            observation_name="llm.groq.completion.stream",
                                            prompt=prompt_obj,
                                        ):
                                            pieces.append(ch)
                                            yield ch

                                    st.write_stream(_gen())
                                    answer = "".join(pieces)
                                else:
                                    answer = complete_groq_chat(
                                        messages,
                                        observation_name="llm.groq.completion",
                                        prompt=prompt_obj,
                                    )
                                    st.markdown(answer)

                                if config.ENABLE_ANSWER_VALIDATION:
                                    validation = validate_answer(
                                        _grounded_slice_for_validation(answer), context
                                    )
                                    vd = validation.to_dict()
                                    _push_validation_scores(vd, stage="initial")

                                    if vd["decision"] == "fail" or vd["confidence"] < int(config.RAG_CONFIDENCE_THRESHOLD):
                                        st.warning("Low confidence detected. Running critic revision pass...")
                                        revised_ok = False
                                        rounds = max(0, int(config.RAG_MAX_REVISION_ROUNDS))
                                        for i in range(rounds):
                                            revised = revise_answer_with_critic(
                                                prompt,
                                                context,
                                                answer,
                                                vd.get("issues", []),
                                                observation_name="llm.groq.critic_revision",
                                            )
                                            revised_validation = validate_answer(
                                                _grounded_slice_for_validation(revised), context
                                            ).to_dict()
                                            trace.append(
                                                f"Critic revision {i+1}: confidence {vd['confidence']}% -> {revised_validation['confidence']}%"
                                            )
                                            if revised_validation["confidence"] >= int(config.RAG_CONFIDENCE_THRESHOLD) and revised_validation["decision"] != "fail":
                                                answer = revised
                                                validation = validate_answer(
                                                    _grounded_slice_for_validation(answer), context
                                                )
                                                _push_validation_scores(
                                                    validation.to_dict(), stage="refined"
                                                )
                                                st.markdown("---")
                                                st.markdown("### Refined answer")
                                                st.markdown(answer)
                                                st.success("Confidence improved after critic revision.")
                                                revised_ok = True
                                                break
                                            vd = revised_validation
                                            answer = revised
                                        if not revised_ok and bool(config.RAG_STRICT_ABSTAIN_ON_FAIL):
                                            abstain = (
                                                "I cannot provide a reliable grounded answer from the current context. "
                                                "Please refine your question with a specific document section, endpoint, "
                                                "or upload additional evidence."
                                            )
                                            answer = abstain + _general_orientation_tail(prompt)
                                            st.error("Answer withheld: confidence remained below threshold after revision.")
                                            st.markdown(answer)
                        finally:
                            if lf and chain_obs is not None:
                                try:
                                    total_ms = (time.perf_counter() - chain_started) * 1000
                                    out_payload = {
                                        "question": prompt,
                                        "context_chars": len(context or ""),
                                        # Context preview is consumed by the Langfuse
                                        # LLM-as-a-Judge "Hallucination/Faithfulness"
                                        # evaluator to score the answer against the
                                        # documents we actually retrieved.
                                        "context_preview": (context or "")[:4000],
                                        "answer_preview": (answer or "")[:6000],
                                        "total_latency_ms": round(total_ms, 2),
                                    }
                                    chain_obs.update(
                                        output=out_payload,
                                        metadata={
                                            "validation_enabled": bool(config.ENABLE_ANSWER_VALIDATION),
                                        },
                                    )
                                    set_current_trace_io(
                                        question=prompt,
                                        answer=answer or "",
                                        context_preview=(context or "")[:4000],
                                        extra_input={
                                            "agentic_rag": use_agentic,
                                            "stream_answers": use_stream,
                                        },
                                        extra_output={
                                            "answer_preview": out_payload["answer_preview"],
                                            "total_latency_ms": out_payload["total_latency_ms"],
                                        },
                                    )
                                except Exception:
                                    pass
                            mark_current_span_ok()
                            flush_langfuse()
                            turn_ms = (time.perf_counter() - chain_started) * 1000
                            record_rag_turn(
                                "company_knowledge",
                                turn_ms,
                                success=turn_ok,
                                context_chars=len(context or ""),
                                agentic=use_agentic,
                            )
                            log_event(
                                "rag.turn.complete",
                                attributes={
                                    "module": "company_knowledge",
                                    "latency_ms": round(turn_ms, 2),
                                    "context_chars": len(context or ""),
                                    "agentic_rag": use_agentic,
                                },
                            )
                            flush_openobserve()

                st.session_state.rag_panel_trace = list(trace)
                st.session_state.rag_panel_validation = (
                    validation.to_dict() if validation is not None else None
                )

                st.session_state.rag_chat_history.append({"role": "assistant", "content": answer})
                st.session_state.last_rag_exchange = {
                    "question": prompt,
                    "answer": answer,
                    "validation": validation.to_dict() if validation else {},
                    "context_chars": len(context or ""),
                    "trace_id": captured_trace_id,
                }

            except Exception as e:
                error_msg = f"Error generating response: {str(e)}"
                mark_current_span_error(str(e))
                record_rag_error("company_knowledge", type(e).__name__, str(e))
                log_event(f"rag.turn.error | {error_msg}", level=40)
                flush_openobserve()
                st.error(error_msg)
                st.session_state.rag_panel_trace = []
                st.session_state.rag_panel_validation = None
                st.session_state.rag_chat_history.append({"role": "assistant", "content": error_msg})

    _render_rag_quality_panel()

    if st.session_state.rag_chat_history:
        st.markdown("---")
        if st.button("🗑️ Clear Chat History"):
            st.session_state.rag_chat_history = []
            st.session_state.pop("rag_panel_trace", None)
            st.session_state.pop("rag_panel_validation", None)
            st.session_state.pop("last_rag_exchange", None)
            reset_session_id("company_knowledge")
            st.rerun()
