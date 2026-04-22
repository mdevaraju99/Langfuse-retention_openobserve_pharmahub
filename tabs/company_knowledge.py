"""
Company Knowledge Page (Multi-Document RAG with Neo4j)
Enhanced: streaming answers, spell hints, agentic retrieval, capacity readout.
"""
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
    ingest_document,
    ingest_documents_batch,
    get_rag_context,
    get_documents_list,
    get_document_media_assets,
    delete_document,
    clear_all_documents,
)
from utils.spellcheck_util import suggest_for_text


RAG_SYSTEM_PROMPT = """You are an expert pharmaceutical knowledge assistant with deep expertise in clinical trials, drug mechanisms, and regulatory affairs. You are analyzing multiple documents simultaneously.

INSTRUCTIONS:
1. Answer based ONLY on the provided context. Never hallucinate.
2. Always cite the exact source document in brackets like [document_name.pdf] after each fact.
3. Use rich markdown formatting: headers (##, ###), bullet points, **bold**, tables where helpful.
4. For COMPARISON questions: use a markdown table and label sources per row.
5. For SAFETY questions: separate severity levels clearly.
6. Always end with a short conclusion section.

If the context is insufficient, say so explicitly and do not invent facts."""


def show():
    st.markdown(
        '<h2 class="gradient-header">🏢 Multi-Document Knowledge Base</h2>',
        unsafe_allow_html=True,
    )
    st.markdown(
        "Upload pharmaceutical PDFs and ask questions across them. "
        "**New:** streaming replies, spell hints, optional **agentic retrieval**, richer PDF/table extraction, and explicit **capacity limits**."
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
        show_spell = st.checkbox("Spell-check hints on questions", value=True)

        st.markdown("---")
        st.markdown("### 📏 Hub capacity (configured)")
        st.markdown(
            f"- Max PDF size: **{config.RAG_MAX_PDF_MB} MB**\n"
            f"- Max pages indexed per PDF: **{config.RAG_MAX_PDF_PAGES}**\n"
            f"- Max chunks stored per document: **{config.RAG_MAX_CHUNKS_PER_DOC}**\n"
            f"- Max ingest characters (soft cap): **{config.RAG_MAX_INGEST_CHARS:,}**"
        )
        if docs:
            total_chunks = sum(int(d.get("chunk_count") or 0) for d in docs)
            st.metric("Documents in graph", len(docs))
            st.metric("Total chunks (approx.)", total_chunks)

        st.markdown("---")
        st.markdown("### 📂 Document Upload")

        uploaded_files = st.file_uploader(
            "Upload PDF Documents",
            type=["pdf"],
            accept_multiple_files=True,
            help="PDFs only. Tables are captured as text/markdown blocks when possible (PyMuPDF).",
        )

        if uploaded_files and st.button("📥 Process Documents", use_container_width=True):
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
                    st.write(f"**Type:** {doc.get('doc_type', 'unknown')}")
                    st.write(f"**Uploaded:** {doc.get('upload_date', 'N/A')}")
                    st.write(f"**Chunks:** {doc.get('chunk_count', 0)}")
                    st.write(
                        f"**Media:** tables={int(doc.get('table_count') or 0)}, "
                        f"images={int(doc.get('image_count') or 0)}, "
                        f"formula-like={int(doc.get('formula_like_count') or 0)}, "
                        f"chart-like={int(doc.get('chart_like_count') or 0)}"
                    )
                    if st.checkbox(
                        "Show rich-media previews",
                        value=False,
                        key=f"media_preview_{idx}",
                    ):
                        media = get_document_media_assets(doc.get("filename", ""))
                        if media:
                            tabs = st.tabs(["Tables", "Images", "Formulas", "Charts"])
                            with tabs[0]:
                                trows = media.get("tables", [])[: int(config.RAG_MAX_MEDIA_TABLE_PREVIEWS)]
                                if trows:
                                    for t_i, t in enumerate(trows, start=1):
                                        st.caption(f"Table {t_i} (page {t.get('page', '-')})")
                                        st.markdown(t.get("markdown", ""))
                                else:
                                    st.caption("No table previews extracted.")
                            with tabs[1]:
                                imgs = media.get("images", [])[: int(config.RAG_MAX_MEDIA_IMAGES)]
                                if imgs:
                                    for im in imgs:
                                        st.image(im.get("path", ""), caption=f"Page {im.get('page', '-')}")
                                else:
                                    st.caption("No image previews extracted.")
                            with tabs[2]:
                                formulas = media.get("formula_snippets", [])[: int(config.RAG_MAX_MEDIA_SNIPPETS)]
                                if formulas:
                                    for f in formulas:
                                        st.markdown(f"- Page {f.get('page', '-')}: `{f.get('text', '')}`")
                                else:
                                    st.caption("No formula-like snippets detected.")
                            with tabs[3]:
                                charts = media.get("chart_snippets", [])[: int(config.RAG_MAX_MEDIA_SNIPPETS)]
                                if charts:
                                    for c in charts:
                                        st.markdown(f"- Page {c.get('page', '-')}: {c.get('text', '')}")
                                else:
                                    st.caption("No chart/graph snippets detected.")
                        else:
                            st.caption("No rich-media preview manifest found yet for this document.")

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
        st.markdown("### 🔍 Explore Graph")
        st.markdown(
            """
Open [Neo4j Browser](http://localhost:7474) to visualize your knowledge graph.

**Recommended Queries:**
```cypher
MATCH (d:Document) RETURN d LIMIT 25
MATCH (e:Entity) RETURN e LIMIT 25
MATCH (c1:Chunk)-[s:SIMILAR_TO]->(c2:Chunk) RETURN c1, s, c2 LIMIT 10
```
            """
        )

    st.markdown("---")

    if not docs:
        st.info("👈 Please upload documents in the sidebar to start chatting.")
        st.markdown(
            """
### 💡 What changed vs the original POC

| Area | Before | Now |
|------|--------|-----|
| Answers | Appear all at once after spinner | Optional **token streaming** |
| Retrieval | Mostly single-shot embedding search | Optional **agentic** rewrite + relevance gate + retry |
| PDFs | `pypdf` text only | **PyMuPDF** + best-effort **table blocks** + size/page/chunk caps |
| Quality of life | None | **Spell hints** on questions + **capacity** readout |

### Example prompts (multi-doc)

- “Compare inclusion criteria in protocol.pdf vs enrolled population in csr.pdf.”
- “List serious adverse events mentioned across all uploaded documents with sources.”
            """
        )
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

        if show_spell:
            hints = suggest_for_text(prompt)
            if hints:
                hstr = ", ".join([f"`{a}` → `{b}`" for a, b in hints])
                st.caption(f"Spell hints: {hstr}")

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
                else:
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
                            st.session_state.rag_chat_history.append({"role": "assistant", "content": answer})
                            st.session_state.last_rag_exchange = {
                                "question": prompt,
                                "answer": answer,
                                "validation": {},
                                "context_chars": 0,
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
                    else:
                        messages = [
                            {"role": "system", "content": RAG_SYSTEM_PROMPT},
                            {
                                "role": "user",
                                "content": f"CONTEXT FROM DOCUMENTS:\n{context}\n\nQUESTION:\n{prompt}",
                            },
                        ]

                        if use_stream:
                            pieces: list[str] = []

                            def _gen():
                                for ch in stream_groq_chat(messages):
                                    pieces.append(ch)
                                    yield ch

                            st.write_stream(_gen())
                            answer = "".join(pieces)
                        else:
                            answer = complete_groq_chat(messages)
                            st.markdown(answer)

                        if config.ENABLE_ANSWER_VALIDATION:
                            validation = validate_answer(answer, context)
                            vd = validation.to_dict()
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Confidence", f"{vd['confidence']}%")
                            c2.metric("Citations", str(vd["citation_count"]))
                            c3.metric("Grounded ratio", f"{int(vd['grounded_ratio'] * 100)}%")

                            if vd["decision"] == "fail" or vd["confidence"] < int(config.RAG_CONFIDENCE_THRESHOLD):
                                st.warning("Low confidence detected. Running critic revision pass...")
                                revised_ok = False
                                rounds = max(0, int(config.RAG_MAX_REVISION_ROUNDS))
                                for i in range(rounds):
                                    revised = revise_answer_with_critic(prompt, context, answer, vd.get("issues", []))
                                    revised_validation = validate_answer(revised, context).to_dict()
                                    trace.append(
                                        f"Critic revision {i+1}: confidence {vd['confidence']}% -> {revised_validation['confidence']}%"
                                    )
                                    if revised_validation["confidence"] >= int(config.RAG_CONFIDENCE_THRESHOLD) and revised_validation["decision"] != "fail":
                                        answer = revised
                                        validation = validate_answer(answer, context)
                                        st.markdown("---")
                                        st.markdown("### Refined answer")
                                        st.markdown(answer)
                                        st.success("Confidence improved after critic revision.")
                                        revised_ok = True
                                        break
                                    vd = revised_validation
                                    answer = revised
                                if not revised_ok and bool(config.RAG_STRICT_ABSTAIN_ON_FAIL):
                                    answer = (
                                        "I cannot provide a reliable grounded answer from the current context. "
                                        "Please refine your question with a specific document section, endpoint, "
                                        "or upload additional evidence."
                                    )
                                    st.error("Answer withheld: confidence remained below threshold after revision.")
                                    st.markdown(answer)
                            elif vd["decision"] == "warn":
                                st.info("Partial grounding detected. Verify critical claims against source docs.")
                            if vd["issues"]:
                                with st.expander("Validation details", expanded=False):
                                    st.markdown("\n".join([f"- {x}" for x in vd["issues"]]))

                if trace:
                    with st.expander("Agentic trace (retrieval)", expanded=False):
                        st.markdown("\n\n".join(trace))

                st.session_state.rag_chat_history.append({"role": "assistant", "content": answer})
                st.session_state.last_rag_exchange = {
                    "question": prompt,
                    "answer": answer,
                    "validation": validation.to_dict() if validation else {},
                    "context_chars": len(context or ""),
                }

            except Exception as e:
                error_msg = f"Error generating response: {str(e)}"
                st.error(error_msg)
                st.session_state.rag_chat_history.append({"role": "assistant", "content": error_msg})

    if st.session_state.rag_chat_history:
        st.markdown("---")
        feedback_comment = st.text_input(
            "Feedback note (optional)",
            value="",
            key="rag_feedback_comment",
            placeholder="What was good or what needs correction?",
        )
        b1, b2 = st.columns(2)
        with b1:
            if st.button("🗑️ Clear Chat History"):
                st.session_state.rag_chat_history = []
                st.rerun()
        with b2:
            f1, f2 = st.columns(2)
            up_clicked = f1.button("👍 Save +1", use_container_width=True, type="secondary")
            down_clicked = f2.button("👎 Save -1", use_container_width=True, type="secondary")
            if up_clicked or down_clicked:
                ex = st.session_state.get("last_rag_exchange", {})
                if ex:
                    target = append_feedback(
                        question=ex.get("question", ""),
                        answer=ex.get("answer", ""),
                        rating="thumbs_up" if up_clicked else "thumbs_down",
                        comment=feedback_comment,
                        metadata={"validation": ex.get("validation", {}), "context_chars": ex.get("context_chars", 0)},
                    )
                    st.success(f"Saved feedback to {target}")
                else:
                    st.info("No response yet to save feedback for.")
