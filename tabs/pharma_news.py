"""
Pharma News Page - uses client-side shuffle rotation
(NewsAPI free tier does not support page/from params)
"""
import streamlit as st
import random
from utils.data_fetchers import fetch_pharma_news
from utils.pharma_guardrails import (
    guardrail_enabled,
    filter_pharma_relevant_news,
    user_search_allowed,
)
from components.cards import news_card
from utils.formatters import truncate_text
from utils.spellcheck_util import normalize_query_text, suggest_for_text
from datetime import datetime
import config

def _build_news_query(raw_input: str, normalized: str, strict_pharma: bool) -> str:
    base_query = (normalized or raw_input or "").strip()
    if not base_query:
        return str(config.PHARMA_NEWS_DEFAULT_QUERY).strip()
    if not strict_pharma:
        return base_query
    context_query = str(config.PHARMA_NEWS_CONTEXT_QUERY).strip()
    if not context_query:
        return base_query
    return f"({base_query}) AND ({context_query})"


def show():
    st.markdown('<h2 class="gradient-header">📰 Pharma News</h2>', unsafe_allow_html=True)
    st.markdown("Latest pharmaceutical industry news from around the world")

    # Initialize session state
    if "news_shuffle_seed" not in st.session_state:
        st.session_state.news_shuffle_seed = 0
    if "last_news_state_key" not in st.session_state:
        st.session_state.last_news_state_key = ""

    # Search and filters
    col1, col2 = st.columns([3, 1])

    with col1:
        search_query = st.text_input(
            "Search news",
            placeholder="e.g., COVID vaccine, FDA approval, drug trials...",
            key="news_search_input",
            label_visibility="collapsed"
        )

    with col2:
        page_size = st.selectbox(
            "Articles to show",
            options=[5, 10, 20],
            index=1,
            label_visibility="collapsed"
        )

    strict_pharma = st.checkbox(
        "Strict pharma context (recommended)",
        value=bool(guardrail_enabled()),
        help="Adds industry/clinical keywords to the NewsAPI query. With **Pharma relevance (all modules)** "
        "on in the sidebar, fetched articles are post-filtered so items with no pharma/clinical terms are dropped.",
        key="news_strict_pharma_context",
    )

    raw_input = (search_query or "").strip()
    normalized, auto_corrections = normalize_query_text(raw_input) if raw_input else ("", [])
    if raw_input:
        hints = suggest_for_text(raw_input)
        extra = [h for h in hints if h not in auto_corrections]
        if auto_corrections:
            pairs = ", ".join([f"`{a}` → `{b}`" for a, b in auto_corrections])
            st.caption(f"**Spell check:** auto-corrected {pairs} for search.")
        elif extra:
            pairs = ", ".join([f"`{a}` → `{b}`" for a, b in extra])
            st.caption(f"**Spell hints:** {pairs}")

    force_general_pharma_feed = False
    off_topic_term: str | None = None

    if raw_input and not user_search_allowed(raw_input, normalized):
        st.warning(
            f"**`{raw_input}`** is **not** treated as a pharmaceutical or clinical search term. "
            "It does not match our in-domain vocabulary (drugs, diseases, trials, regulators, biotech, etc.). "
            "We will not run a news search **on that word**, because it is outside the pharma scope of this hub."
        )
        force_general_pharma_feed = st.checkbox(
            "Show a **general pharma / biotech headline feed** instead (my words are **not** sent to NewsAPI)",
            value=False,
            key="news_browse_general_without_intent",
        )
        if not force_general_pharma_feed:
            st.info(
                "**Try:** vaccine, oncology, Pfizer, clinical trial, diabetes, FDA, biosimilar — "
                "or turn off **Pharma relevance (all modules)** in the sidebar to search without this vocabulary check."
            )
            return
        off_topic_term = raw_input

    strict_for_query = strict_pharma or guardrail_enabled()
    if force_general_pharma_feed:
        query = _build_news_query("", "", strict_for_query)
    else:
        query = _build_news_query(raw_input, normalized, strict_for_query)

    # Reset shuffle seed when search text or “general feed” mode changes
    news_state_key = f"{search_query}|general:{int(force_general_pharma_feed)}"
    if news_state_key != st.session_state.get("last_news_state_key"):
        st.session_state.news_shuffle_seed = 0
        st.session_state.last_news_state_key = news_state_key

    # Fetch a large batch (cached) - no page/from params (free tier limitation)
    with st.spinner("🔍 Fetching latest pharma news..."):
        all_articles = fetch_pharma_news(query=query, page_size=100)
        # Dynamic fallback: if strict context is too narrow, retry with user/base query.
        if not all_articles and raw_input and not force_general_pharma_feed:
            relaxed_query = (normalized or raw_input).strip()
            if relaxed_query and relaxed_query != query:
                all_articles = fetch_pharma_news(query=relaxed_query, page_size=100)
        # Final fallback: default pharma stream.
        if not all_articles:
            all_articles = fetch_pharma_news(
                query=str(config.PHARMA_NEWS_DEFAULT_QUERY).strip(),
                page_size=100,
            )

    raw_count = len(all_articles)
    all_articles = filter_pharma_relevant_news(all_articles)
    if guardrail_enabled() and raw_count and not all_articles:
        st.warning(
            "No articles matched the pharma relevance filter after fetch. "
            "Try a more specific clinical or industry term, or turn off **Pharma relevance (all modules)** in the sidebar."
        )
        return

    if not all_articles:
        st.warning("⚠️ No news articles found. Try a different search term or check your API key.")
        st.info("""
        **Tip:** Get a free NewsAPI key at https://newsapi.org/register

        Then set in `.env`:
        ```
        NEWSAPI_KEY=your_key_here
        ```
        """)
        return

    # Shuffle the full list using the current seed, then slice
    seed = st.session_state.news_shuffle_seed
    shuffled = all_articles.copy()
    random.Random(seed).shuffle(shuffled)
    articles = shuffled[:page_size]

    total_sets = max(1, len(all_articles) // page_size)
    current_set = (seed % total_sets) + 1

    if off_topic_term:
        st.info(
            f"You typed **`{off_topic_term}`** (not a pharma/clinical search term). "
            "What follows is a **general pharmaceutical and biotech industry news** sample from NewsAPI — "
            "recent in-domain headlines from our default query, **not** matched to that word."
        )
    elif raw_input:
        st.caption(
            "**What you’re seeing:** keyword matches on NewsAPI (title + summary): your terms must appear in the article text, "
            "together with our pharma scope. This is **not** semantic “similarity” and not a free-form answer — only industry/clinical news links."
        )

    scope_note = " (pharma-filtered)" if guardrail_enabled() else ""
    st.success(
        f"✅ Showing {len(articles)} of {len(all_articles)} articles{scope_note}  |  Set {current_set} of {total_sets}"
    )

    # Display articles
    for article in articles:
        title = article.get("title", "No title")
        description = article.get("description", "No description available")
        source = article.get("source", {}).get("name", "Unknown")
        published_at = article.get("publishedAt", "")
        url = article.get("url", "#")

        try:
            date_obj = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
            formatted_date = date_obj.strftime("%B %d, %Y")
        except Exception:
            formatted_date = published_at

        description = truncate_text(description, 200)

        news_card(
            title=title,
            description=description,
            source=source,
            date=formatted_date,
            url=url
        )

    # Navigation buttons (fixed grid so alignment does not jump)
    st.markdown("<br>", unsafe_allow_html=True)
    nav_container = st.container()
    with nav_container:
        col_prev, col_refresh, col_next = st.columns(3)

        with col_prev:
            if st.button(
                "⬅️ Previous Set",
                use_container_width=True,
                disabled=(seed == 0),
            ):
                st.session_state.news_shuffle_seed = max(0, seed - 1)
                st.rerun()

        with col_refresh:
            if st.button("🔄 Show Different News", use_container_width=True, type="primary"):
                st.session_state.news_shuffle_seed = seed + 1
                st.rerun()

        with col_next:
            if st.button("Next Set ➡️", use_container_width=True):
                st.session_state.news_shuffle_seed = seed + 1
                st.rerun()
