"""
Clinical Trials Page — uses client-side shuffle rotation for refresh variety
"""
import streamlit as st
import random
from utils.data_fetchers import fetch_clinical_trials
import pandas as pd


def show():
    st.markdown('<h2 class="gradient-header">🔬 Clinical Trials</h2>', unsafe_allow_html=True)
    st.markdown("Search clinical trials from ClinicalTrials.gov database")
    
    # Initialize session state
    if "trials_shuffle_seed" not in st.session_state:
        st.session_state.trials_shuffle_seed = 0
    if "last_trials_query" not in st.session_state:
        st.session_state.last_trials_query = ""
    
    # Search interface
    col1, col2 = st.columns([3, 1])
    
    with col1:
        search_query = st.text_input(
            "Search by condition, drug, or sponsor",
            placeholder="e.g., diabetes, cancer, Alzheimer's...",
            label_visibility="collapsed"
        )
    
    with col2:
        page_size = st.selectbox(
            "Trials to show",
            options=[5, 10, 20],
            index=1,
            label_visibility="collapsed"
        )
    
    query = search_query if search_query else "cancer"

    # Reset shuffle seed when query changes
    if search_query != st.session_state.last_trials_query:
        st.session_state.trials_shuffle_seed = 0
        st.session_state.last_trials_query = search_query
    
    # Fetch a large batch (cached)
    with st.spinner("🔍 Searching clinical trials..."):
        all_trials = fetch_clinical_trials(query=query, page_size=100)
    
    if not all_trials:
        st.warning("⚠️ No trials found. Try a different search term.")
        return
    
    # Shuffle the full list using the current seed, then slice
    seed = st.session_state.trials_shuffle_seed
    shuffled = all_trials.copy()
    random.Random(seed).shuffle(shuffled)
    trials = shuffled[:page_size]

    total_sets = max(1, len(all_trials) // page_size)
    current_set = (seed % total_sets) + 1
    
    st.success(f"✅ Showing {len(trials)} of {len(all_trials)} trials  |  Set {current_set} of {total_sets}")
    
    # Display as cards
    for trial in trials:
        with st.container():
            st.markdown(f"""
            <div class="news-card fade-in">
                <div class="news-title">{trial.get('title', 'N/A')}</div>
                <div class="news-meta">
                    <span class="badge" style="background: #6366F120; color: #6366F1; border-color: #6366F150;">
                        {trial.get('nct_id', 'N/A')}
                    </span>
                    <span class="badge" style="background: #10B98120; color: #10B981; border-color: #10B98150;">
                        {trial.get('phase', 'N/A')}
                    </span>
                    <span class="badge" style="background: #F59E0B20; color: #F59E0B; border-color: #F59E0B50;">
                        {trial.get('status', 'N/A')}
                    </span>
                </div>
                <div class="news-meta" style="margin-top: 0.5rem;">
                    <span>👥 Enrollment: {trial.get('enrollment', 'N/A')}</span>
                </div>
                <div style="margin-top: 0.75rem;">
                    <a href="{trial.get('url', '#')}" target="_blank" style="font-size: 0.9rem;">
                        View on ClinicalTrials.gov →
                    </a>
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    # Navigation buttons
    st.markdown("<br>", unsafe_allow_html=True)
    col_prev, col_refresh, col_next = st.columns([1, 2, 1])
    
    with col_prev:
        if seed > 0:
            if st.button("⬅️ Previous Set", use_container_width=True):
                st.session_state.trials_shuffle_seed = max(0, seed - 1)
                st.rerun()
    
    with col_refresh:
        if st.button("🔄 Show Different Trials", use_container_width=True, type="primary"):
            st.session_state.trials_shuffle_seed = seed + 1
            st.rerun()
    
    with col_next:
        if st.button("Next Set ➡️", use_container_width=True):
            st.session_state.trials_shuffle_seed = seed + 1
            st.rerun()
