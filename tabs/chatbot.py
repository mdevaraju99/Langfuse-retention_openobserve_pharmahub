import streamlit as st

import config
from utils.pharma_guardrails import guardrail_enabled
from utils.agentic_rag import complete_groq_chat, stream_groq_chat
from utils.spellcheck_util import suggest_for_text


GENERAL_SYSTEM_PROMPT_STRICT = """You are an expert pharmaceutical knowledge assistant with deep expertise in drugs, diseases, clinical trial phases, and regulatory topics.

STRICT DOMAIN RULE:
- You ONLY answer questions related to the pharmaceutical domain (drugs, clinical trials, healthcare research, regulatory affairs, biotech, etc.).
- If the user asks a question that is NOT related to the pharmaceutical domain, politely decline using this message: "{domain_refusal_text}".
- Do not provide any non-pharma information, even if you know it.

INSTRUCTIONS:
1. Use your general knowledge to provide accurate information about the pharmaceutical industry.
2. Use rich markdown formatting: headers (##, ###), bullet points, and **bold**.
3. Always include a medical disclaimer: "Please consult healthcare professionals for medical advice."
4. Be concise, professional, and helpful.
5. Use emojis where appropriate: 🔬 Research, 💊 Drugs, 🏥 Clinical, ⚖️ Regulatory."""

GENERAL_SYSTEM_PROMPT_OPEN = """You are a helpful assistant. You have strong expertise in drugs, clinical trials, regulatory affairs, and biotech, and you should emphasize accurate, well-sourced-style reasoning when the topic touches healthcare.

INSTRUCTIONS:
1. Answer the user's question directly; you are not restricted to pharma-only topics while **Pharma relevance** is off in the app sidebar.
2. Use rich markdown formatting: headers (##, ###), bullet points, and **bold**.
3. For medical or treatment questions, include: "Please consult healthcare professionals for medical advice."
4. Be concise, professional, and helpful.
5. Use emojis where appropriate: 🔬 Research, 💊 Drugs, 🏥 Clinical, ⚖️ Regulatory."""


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
        messages.append(msg)
    messages.append({"role": "user", "content": question})
    return messages

def _render_llm_response(messages: list, use_stream: bool) -> str:
    if use_stream and config.ENABLE_STREAMING_UI:
        buf: list[str] = []

        def _gen():
            for ch in stream_groq_chat(messages):
                buf.append(ch)
                yield ch

        st.write_stream(_gen())
        return "".join(buf)

    response = complete_groq_chat(messages)
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
    show_spell = st.checkbox(
        "Spell-check hints",
        value=True,
        key="chatbot_spell_toggle",
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

        if show_spell:
            hints = suggest_for_text(user_input)
            if hints:
                hstr = ", ".join([f"`{a}` → `{b}`" for a, b in hints])
                st.caption(f"Spell hints: {hstr}")

        st.session_state.chat_history.append({"role": "user", "content": user_input})

        with st.chat_message("assistant", avatar="🤖"):
            if not config.GROQ_API_KEY:
                response = (
                    "⚠️ Please set your GROQ_API_KEY in the `.env` file to use the chatbot.\n\n"
                    "Get a free API key at: https://console.groq.com/"
                )
                st.markdown(response)
            else:
                try:
                    messages = _build_general_messages(user_input, st.session_state.chat_history[:-1])
                    response = _render_llm_response(messages, use_stream)
                except Exception as e:
                    response = f"❌ Error: {str(e)}\n\nPlease check your GROQ_API_KEY configuration."
                    st.markdown(response)

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
