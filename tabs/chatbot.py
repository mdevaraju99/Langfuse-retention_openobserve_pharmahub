from contextlib import nullcontext
import re

import streamlit as st

import config
from utils.pharma_guardrails import guardrail_enabled
from utils.agentic_rag import complete_groq_chat, stream_groq_chat
from utils.langfuse_trace import (
    apply_trace_context,
    flush_langfuse,
    get_langfuse_client,
    get_session_id,
    get_user_id,
    reset_session_id,
    set_current_trace_io,
)
GENERAL_SYSTEM_PROMPT_STRICT = """You are an expert pharmaceutical knowledge assistant with deep expertise in drugs, diseases, clinical trial phases, and regulatory topics.

OUTPUT STYLE: Answer directly like Llama — no chain-of-thought, no long reasoning preamble. Be concise and professional.

OPENING (required before ## headers):
- Start every substantive answer with **one or two short formal sentences** that frame what you are answering (drug, trial phase, regulatory topic, etc.). Professional analyst tone.
- Then use ## headers and bullets. Do NOT jump straight to the first header without an opening line.

STRICT DOMAIN RULE:
- You ONLY answer questions related to the pharmaceutical domain (drugs, clinical trials, healthcare research, regulatory affairs, biotech, etc.).
- **Greetings and brief pleasantries** (hi, hello, thanks, goodbye): reply warmly in one or two sentences, then invite a pharma question. Do NOT use the refusal message for greetings.
- If the user asks a substantive question that is NOT related to the pharmaceutical domain, politely decline using this message: "{domain_refusal_text}".
- Do not provide any non-pharma information, even if you know it.

INSTRUCTIONS:
1. Use your general knowledge to provide accurate information about the pharmaceutical industry.
2. Use rich markdown formatting: headers (##, ###), bullet points, and **bold**.
3. Always include a medical disclaimer: "Please consult healthcare professionals for medical advice."
4. Be concise, professional, and helpful.
5. Use emojis where appropriate: 🔬 Research, 💊 Drugs, 🏥 Clinical, ⚖️ Regulatory."""

GENERAL_SYSTEM_PROMPT_OPEN = """You are a helpful assistant. You have strong expertise in drugs, clinical trials, regulatory affairs, and biotech, and you should emphasize accurate, well-sourced-style reasoning when the topic touches healthcare.

OUTPUT STYLE: Answer directly like Llama — no chain-of-thought, no long reasoning preamble. Be concise.

OPENING (required before ## headers):
- Start every substantive answer with **one or two short formal sentences** that frame the topic, then ## headers and bullets.

INSTRUCTIONS:
1. Answer the user's question directly; you are not restricted to pharma-only topics while **Pharma relevance** is off in the app sidebar.
2. Use rich markdown formatting: headers (##, ###), bullet points, and **bold**.
3. For medical or treatment questions, include: "Please consult healthcare professionals for medical advice."
4. Be concise, professional, and helpful.
5. Use emojis where appropriate: 🔬 Research, 💊 Drugs, 🏥 Clinical, ⚖️ Regulatory."""


_GREETING_ONLY = re.compile(
    r"^\s*(hi|hello|hey|hiya|howdy|greetings|good\s+(morning|afternoon|evening|day))[\s!.?,]*$",
    re.IGNORECASE,
)
_THANKS_ONLY = re.compile(r"^\s*(thanks|thank\s+you|thx|ty)[\s!.?,]*$", re.IGNORECASE)
_BYE_ONLY = re.compile(r"^\s*(bye|goodbye|see\s+you|take\s+care)[\s!.?,]*$", re.IGNORECASE)


def _is_small_talk(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(_GREETING_ONLY.match(t) or _THANKS_ONLY.match(t) or _BYE_ONLY.match(t))


def _small_talk_response(text: str) -> str:
    t = (text or "").strip().lower()
    if _THANKS_ONLY.match(t):
        return (
            "You're welcome! Ask me anything about **drugs**, **clinical trials**, "
            "**regulatory affairs**, or **biotech**."
        )
    if _BYE_ONLY.match(t):
        return "Goodbye! Come back anytime with pharma questions."
    return (
        "Hello! I'm your **Pharma Knowledge** assistant. "
        "Ask me about drugs, clinical trials, regulatory guidance, or biotech — I'm here to help.\n\n"
        "*Please consult healthcare professionals for medical advice.*"
    )


def _build_general_messages(question: str, chat_history: list) -> list:
    enforce_domain = bool(getattr(config, "CHATBOT_ENFORCE_DOMAIN_ONLY", True)) and guardrail_enabled()
    if enforce_domain:
        prompt = GENERAL_SYSTEM_PROMPT_STRICT.format(
            domain_refusal_text=config.CHATBOT_DOMAIN_REFUSAL_TEXT,
        )
    else:
        prompt = GENERAL_SYSTEM_PROMPT_OPEN
    messages = [{"role": "system", "content": prompt}]
    for msg in chat_history[-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": question})
    return messages

def _render_llm_response(messages: list, use_stream: bool) -> str:
    if use_stream and config.ENABLE_STREAMING_UI:
        buf: list[str] = []

        def _gen():
            for ch in stream_groq_chat(messages, observation_name="llm.groq.completion.stream"):
                buf.append(ch)
                yield ch

        st.write_stream(_gen())
        return "".join(buf)

    response = complete_groq_chat(messages, observation_name="llm.groq.completion")
    st.markdown(response)
    return response


def show():
    st.markdown(
        '<h2 class="gradient-header">💬 Pharma Knowledge Chatbot</h2>',
        unsafe_allow_html=True,
    )
    st.markdown(
        "Ask pharma questions with **ChatGPT-like conversational flow** using Groq. "
        "This tab uses **general pharma intelligence only**."
    )

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    use_stream = st.checkbox(
        "Stream answers",
        value=bool(config.ENABLE_STREAMING_UI),
        key="chatbot_stream_toggle",
    )
    st.caption("Document-grounded Q&A is available in the **Company Knowledge** tab.")

    for message in st.session_state.chat_history:
        role = message["role"]
        content = message["content"]
        if role == "user":
            with st.chat_message("user", avatar="👤"):
                st.markdown(content)
        else:
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(content)

    pending = st.session_state.pop("chat_pending_question", None)
    user_input = st.chat_input("Ask me anything about pharma...")
    if pending and not user_input:
        user_input = pending

    if user_input:
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_input)

        st.session_state.chat_history.append({"role": "user", "content": user_input})

        with st.chat_message("assistant", avatar="🤖"):
            if not config.GROQ_API_KEY:
                response = (
                    "⚠️ Please set your GROQ_API_KEY in the `.env` file to use the chatbot.\n\n"
                    "Get a free API key at: https://console.groq.com/"
                )
                st.markdown(response)
            else:
                lf = get_langfuse_client()
                chatbot_session_id = get_session_id("chatbot")
                user_id = get_user_id()
                chain_cm = (
                    lf.start_as_current_observation(
                        name="chatbot",
                        as_type="chain",
                        input={
                            "question": user_input,
                            "stream_answers": bool(use_stream),
                            "guardrail_enabled": guardrail_enabled(),
                        },
                    )
                    if lf
                    else nullcontext()
                )
                response = ""
                trace_ctx = apply_trace_context(
                    lf,
                    session_id=chatbot_session_id,
                    user_id=user_id,
                    tags=["chatbot"],
                )
                # chain_cm first so the chain span is the currently active OTel
                # span when apply_trace_context() sets session.id / user.id on it.
                with chain_cm as chain_obs, trace_ctx:
                    try:
                        if _is_small_talk(user_input):
                            response = _small_talk_response(user_input)
                            st.markdown(response)
                        else:
                            messages = _build_general_messages(user_input, st.session_state.chat_history[:-1])
                            response = _render_llm_response(messages, use_stream)
                    except Exception as e:
                        response = f"❌ Error: {str(e)}\n\nPlease check your GROQ_API_KEY configuration."
                        st.markdown(response)
                    finally:
                        if lf and chain_obs is not None:
                            try:
                                chain_obs.update(
                                    output={
                                        "question": user_input,
                                        "answer_preview": (response or "")[:6000],
                                    }
                                )
                                set_current_trace_io(
                                    question=user_input,
                                    answer=response or "",
                                    extra_input={
                                        "stream_answers": bool(use_stream),
                                        "guardrail_enabled": guardrail_enabled(),
                                    },
                                    extra_output={
                                        "answer_preview": (response or "")[:6000],
                                    },
                                )
                            except Exception:
                                pass
                        flush_langfuse()

        st.session_state.chat_history.append({"role": "assistant", "content": response})
        st.rerun()

    with st.sidebar:
        st.markdown("---")
        st.markdown("### 💡 Example Questions")

        examples = [
            "What is metformin used for?",
            "Explain Phase 3 clinical trials",
            "What are common adverse effects of statins?",
            "How does FDA drug approval work?",
            "Latest in cancer immunotherapy",
        ]

        for example in examples:
            if st.button(f"💬 {example}", use_container_width=True, key=f"ex_{example}"):
                st.session_state.chat_pending_question = example
                st.rerun()

        st.markdown("---")

        if st.button("🗑️ Clear Chat History", use_container_width=True, type="secondary"):
            st.session_state.chat_history = []
            reset_session_id("chatbot")
            st.rerun()

    if not st.session_state.chat_history:
        st.info(
            """
👋 **Welcome to the Pharma Knowledge Chatbot!**

I can help you with:
- Drug information and usage
- Clinical trial explanations
- Regulatory guidance
- Pharma industry trends and news

💡 **Need document-grounded responses?** Use the **Company Knowledge** tab.
            """
        )

        if not config.GROQ_API_KEY:
            st.warning(
                """
⚠️ **Groq API Key Required**

To use the chatbot, get a free API key at https://console.groq.com/

Then create a `.env` file with:
```
GROQ_API_KEY=your_key_here
```
                """
            )
