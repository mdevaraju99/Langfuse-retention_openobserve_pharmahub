"""
Analytics Dashboard Page — all data fetched live from real APIs.
Cache is 24 hours so numbers refresh daily.
"""
import streamlit as st
from utils.data_fetchers import (
    fetch_analytics_data,
    fetch_trials_by_phase,
    fetch_therapeutic_area_data,
    fetch_monthly_fda_approvals,
)
from components.cards import kpi_card
from utils.formatters import format_number
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime


def show():
    st.markdown('<h2 class="gradient-header">📊 Analytics Dashboard</h2>', unsafe_allow_html=True)
    st.markdown("Real-time pharmaceutical industry metrics and insights — **refreshed every 24 hours**")

    # ── KPI Cards ─────────────────────────────────────────────────────────────
    st.markdown("### 📌 Key Performance Indicators")

    with st.spinner("📈 Loading live analytics data..."):
        data = fetch_analytics_data()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        kpi_card(
            label="FDA Approved Drugs",
            value=format_number(data.get("total_drugs", 0)),
            icon="💊"
        )

    with col2:
        kpi_card(
            label="Active Clinical Trials",
            value=format_number(data.get("active_trials", 0)),
            icon="🔬"
        )

    with col3:
        kpi_card(
            label="Research Papers (This Month)",
            value=format_number(data.get("recent_papers", 0)),
            icon="📚"
        )

    with col4:
        kpi_card(
            label="News Articles Loaded",
            value=format_number(data.get("news_count", 0)),
            icon="📰"
        )

    st.caption(f"⏰ Data cached for 24 hours. Last loaded: {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Charts ────────────────────────────────────────────────────────────────
    st.markdown("### 📈 Trends & Insights")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Clinical Trials by Phase (Recruiting)")
        with st.spinner("Loading phase data..."):
            phase_data = fetch_trials_by_phase()

        if any(v > 0 for v in phase_data.values()):
            fig1 = px.pie(
                names=list(phase_data.keys()),
                values=list(phase_data.values()),
                color_discrete_sequence=["#6366F1", "#8B5CF6", "#A855F7", "#C084FC"],
                hole=0.4
            )
            fig1.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#E5E7EB", size=12),
                margin=dict(l=0, r=0, t=20, b=0)
            )
            st.plotly_chart(fig1, use_container_width=True)
            st.caption("ℹ️ Phase distribution is based on a sample of the most recent 1,000 recruiting trials.")
        else:
            st.info("Phase data unavailable — ClinicalTrials.gov API may be temporarily slow.")

    with col2:
        st.markdown("#### Monthly FDA Drug Approvals (Last 6 Months)")
        with st.spinner("Loading FDA approvals..."):
            fda_data = fetch_monthly_fda_approvals()

        months = fda_data.get("months", [])
        approvals = fda_data.get("approvals", [])

        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=months,
            y=approvals,
            mode='lines+markers',
            line=dict(color='#6366F1', width=3),
            marker=dict(size=10, color='#8B5CF6'),
            fill='tozeroy',
            fillcolor='rgba(99, 102, 241, 0.1)',
            hovertemplate='%{x}: %{y} approvals<extra></extra>'
        ))
        fig2.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#E5E7EB"),
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)"),
            margin=dict(l=0, r=0, t=20, b=0)
        )
        st.plotly_chart(fig2, use_container_width=True)

    # ── Therapeutic Areas ─────────────────────────────────────────────────────
    st.markdown("### 🎯 Top Therapeutic Areas")

    with st.spinner("Loading therapeutic area data..."):
        ta_data = fetch_therapeutic_area_data()

    areas = ta_data.get("areas", [])
    trial_counts = ta_data.get("trial_counts", [])
    paper_counts = ta_data.get("paper_counts", [])

    if areas and (any(trial_counts) or any(paper_counts)):
        areas_df = pd.DataFrame({
            "Therapeutic Area": areas,
            "Active Trials": trial_counts,
            "Research Papers (YTD)": paper_counts,
        })

        fig3 = go.Figure()
        fig3.add_trace(go.Bar(
            name='Active Trials',
            x=areas_df["Therapeutic Area"],
            y=areas_df["Active Trials"],
            marker_color='#6366F1',
            hovertemplate='%{x}: %{y} trials<extra></extra>'
        ))
        fig3.add_trace(go.Bar(
            name='Research Papers (YTD)',
            x=areas_df["Therapeutic Area"],
            y=areas_df["Research Papers (YTD)"],
            marker_color='#8B5CF6',
            hovertemplate='%{x}: %{y} papers<extra></extra>'
        ))
        fig3.update_layout(
            barmode='group',
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#E5E7EB"),
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=0, r=0, t=40, b=0)
        )
        st.plotly_chart(fig3, use_container_width=True)

        # Raw numbers table
        with st.expander("📋 View raw numbers"):
            st.dataframe(areas_df, use_container_width=True, hide_index=True)
    else:
        st.info("Therapeutic area data unavailable. APIs may be temporarily slow. Try refreshing.")

    # ── Manual Refresh ────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.info("💡 Data auto-refreshes every **24 hours**. Click below to force a refresh now.")
    if st.button("🔄 Force Refresh Analytics", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()
