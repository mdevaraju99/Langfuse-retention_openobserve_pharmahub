"""
Research Papers Page
"""
import streamlit as st
from utils.data_fetchers import fetch_research_papers
from components.cards import paper_card


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

    query = search_query if search_query else "pharmaceutical drug development"
    current_page = st.session_state.papers_page

    # Page indicator
    st.caption(f"📄 Page {current_page} — sorted by most recent")
    
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
    
    # Navigation buttons
    st.markdown("<br>", unsafe_allow_html=True)
    col_prev, col_refresh, col_next = st.columns([1, 2, 1])
    
    with col_prev:
        if current_page > 1:
            if st.button("⬅️ Previous", use_container_width=True):
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
