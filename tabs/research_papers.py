"""
Research Papers Page
"""
import streamlit as st
from utils.data_fetchers import fetch_research_papers
from utils.pharma_guardrails import (
    guardrail_enabled,
    enrich_pubmed_query,
    user_search_allowed,
)
from components.cards import paper_card
from utils.spellcheck_util import normalize_query_text, suggest_for_text


def show():
    st.markdown('<h2 class="gradient-header">📚 Research Papers</h2>', unsafe_allow_html=True)
    st.markdown("Search pharmaceutical research papers from PubMed")
    
    # Initialize page counter in session state
    if "papers_page" not in st.session_state:
        st.session_state.papers_page = 1
    
    # Search interface
    col1, col2 = st.columns([3, 1])
    
    with col1:
        search_query = st.text_input(
            "Search papers",
            placeholder="e.g., cancer immunotherapy, diabetes treatment, COVID-19...",
            label_visibility="collapsed"
        )
    
    with col2:
        max_results = st.selectbox(
            "Results",
            options=[5, 10, 20, 50],
            index=1,
            label_visibility="collapsed"
        )
    
    # Reset to page 1 if search query changes
    if "last_papers_query" not in st.session_state:
        st.session_state.last_papers_query = ""
    if search_query != st.session_state.last_papers_query:
        st.session_state.papers_page = 1
        st.session_state.last_papers_query = search_query

    raw_input = (search_query or "").strip()
    normalized, auto_corrections = normalize_query_text(raw_input) if raw_input else ("", [])
    if raw_input:
        hints = suggest_for_text(raw_input)
        extra = [h for h in hints if h not in auto_corrections]
        if auto_corrections:
            pairs = ", ".join([f"`{a}` → `{b}`" for a, b in auto_corrections])
            st.caption(f"**Spell check:** auto-corrected {pairs} for PubMed search.")
        elif extra:
            pairs = ", ".join([f"`{a}` → `{b}`" for a, b in extra])
            st.caption(f"**Spell hints:** {pairs}")

    if raw_input and not user_search_allowed(raw_input, normalized):
        st.warning(
            f"**`{raw_input}`** is **not** treated as a pharmaceutical or clinical search term. "
            "It does not match our in-domain vocabulary (drugs, diseases, mechanisms, trials, biotech). "
            "PubMed search is not run on that word while **Pharma relevance** is on."
        )
        st.info(
            "**Try:** immunotherapy, metformin, cardiovascular, randomized trial — "
            "or turn off **Pharma relevance (all modules)** in the sidebar."
        )
        return

    query = normalized if raw_input else "pharmaceutical drug development"
    query = enrich_pubmed_query(query)
    current_page = st.session_state.papers_page

    # Page indicator
    st.caption(
        f"📄 Page {current_page} — sorted by most recent"
        + (" — PubMed query includes a pharma scope clause" if guardrail_enabled() else "")
    )
    
    # Fetch papers
    with st.spinner("🔍 Searching PubMed database..."):
        papers = fetch_research_papers(query=query, max_results=max_results, page=current_page)
    
    if not papers:
        st.warning("⚠️ No papers found. Try a different search term.")
        # Reset to page 1 if no results on a higher page
        if current_page > 1:
            st.session_state.papers_page = 1
        return
    
    st.success(f"✅ Found {len(papers)} papers (Page {current_page})")
    
    # Display papers
    for paper in papers:
        title = paper.get("title", "No title")
        authors = paper.get("authors", [])
        author_str = ", ".join(authors[:3])
        if len(authors) > 3:
            author_str += " et al."
        
        journal = paper.get("journal", "N/A")
        date = paper.get("date", "N/A")
        url = paper.get("url", "#")
        
        paper_card(
            title=title,
            authors=author_str if author_str else "Unknown authors",
            journal=journal,
            date=date,
            url=url
        )
    
    # Navigation buttons (fixed grid so alignment does not jump)
    st.markdown("<br>", unsafe_allow_html=True)
    nav_container = st.container()
    with nav_container:
        col_prev, col_refresh, col_next = st.columns(3)
        
        with col_prev:
            if st.button(
                "⬅️ Previous",
                use_container_width=True,
                disabled=(current_page <= 1),
            ):
                st.session_state.papers_page -= 1
                st.cache_data.clear()
                st.rerun()
        
        with col_refresh:
            if st.button("🔄 Refresh / Next Page", use_container_width=True, type="primary"):
                st.session_state.papers_page += 1
                st.cache_data.clear()
                st.rerun()
        
        with col_next:
            if st.button("Next ➡️", use_container_width=True):
                st.session_state.papers_page += 1
                st.cache_data.clear()
                st.rerun()
