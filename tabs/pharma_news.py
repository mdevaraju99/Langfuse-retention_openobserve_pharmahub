"""
Pharma News Page - uses client-side shuffle rotation
(NewsAPI free tier does not support page/from params)
"""
import streamlit as st
import random
from utils.data_fetchers import fetch_pharma_news
from components.cards import news_card
from utils.formatters import truncate_text
from datetime import datetime


def is_pharma_related(query):
    """Check if a query is related to the pharmaceutical domain"""
    if not query or query.strip() == "":
        return True
    
    pharma_keywords = [
        "pharmaceutical", "pharma", "drug", "medicine", "medical", "clinical", "fda", 
        "regulatory", "vaccine", "therapy", "biotech", "healthcare", "life sciences",
        "oncology", "cardiology", "neurology", "diabetes", "infectious", "trial",
        "patient", "doctor", "hospital", "prescription", "pharmacy", "biologic",
        "generic", "health", "cancer", "alzheimer", "heart", "brain", "vaccination",
        "medication", "dose", "tablet", "capsule", "treatment", "cure", "physician"
    ]
    
    query_lower = query.lower()
    return any(keyword in query_lower for keyword in pharma_keywords)


def show():
    st.markdown('<h2 class="gradient-header">📰 Pharma News</h2>', unsafe_allow_html=True)
    st.markdown("Latest pharmaceutical industry news from around the world")

    # Initialize session state
    if "news_shuffle_seed" not in st.session_state:
        st.session_state.news_shuffle_seed = 0
    if "last_news_query" not in st.session_state:
        st.session_state.last_news_query = ""

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

    # Validate search query
    if search_query and not is_pharma_related(search_query):
        st.warning("⚠️ sorry please ask pharma related questions")
        return

    query = search_query if search_query else "pharmaceutical drug"

    # Reset shuffle seed when query changes
    if search_query != st.session_state.last_news_query:
        st.session_state.news_shuffle_seed = 0
        st.session_state.last_news_query = search_query

    # Fetch a large batch (cached) - no page/from params (free tier limitation)
    with st.spinner("🔍 Fetching latest pharma news..."):
        all_articles = fetch_pharma_news(query=query, page_size=100)

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

    st.success(f"✅ Showing {len(articles)} of {len(all_articles)} articles  |  Set {current_set} of {total_sets}")

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

    # Navigation buttons
    st.markdown("<br>", unsafe_allow_html=True)
    col_prev, col_refresh, col_next = st.columns([1, 2, 1])

    with col_prev:
        if seed > 0:
            if st.button("⬅️ Previous Set", use_container_width=True):
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
