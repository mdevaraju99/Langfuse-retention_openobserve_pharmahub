"""
Clinical Trials Page — uses client-side shuffle rotation for refresh variety
"""
import streamlit as st
import random
from utils.data_fetchers import fetch_clinical_trials
from utils.pharma_guardrails import (
    guardrail_enabled,
    enrich_clinical_trials_query,
    user_search_allowed,
)
from utils.spellcheck_util import normalize_query_text, suggest_for_text


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

    raw_input = (search_query or "").strip()
    normalized, auto_corrections = normalize_query_text(raw_input) if raw_input else ("", [])
    if raw_input:
        hints = suggest_for_text(raw_input)
        if hints:
            hint_str = ", ".join([f"`{a}` -> `{b}`" for a, b in hints[:8]])
            st.caption(f"Spell hints: {hint_str}")
        if auto_corrections and normalized and normalized.lower() != raw_input.lower():
            st.caption(f"Using normalized query: `{normalized}`")

    if raw_input and not user_search_allowed(raw_input, normalized):
        st.warning(
            f"**`{raw_input}`** is **not** treated as a pharmaceutical or clinical search term. "
            "It does not match our in-domain vocabulary (conditions, drugs, sponsors, trial concepts). "
            "ClinicalTrials.gov search is not run on that word while **Pharma relevance** is on."
        )
        st.info(
            "**Try:** diabetes, breast cancer, pembrolizumab, NCT number — "
            "or turn off **Pharma relevance (all modules)** in the sidebar."
        )
        return

    query = normalized if normalized else (search_query if search_query else "cancer")
    query = enrich_clinical_trials_query(query)
    if guardrail_enabled():
        st.caption("ClinicalTrials.gov query includes a pharma / intervention scope clause.")

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
