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
import json
from pathlib import Path

from utils.benchmark_runner import run_benchmark_suite
from utils.feedback_tuning_report import load_feedback, build_report, write_report
import config


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
            label="Pharma headlines (NewsAPI)",
            value=format_number(data.get("news_count", 0)),
            icon="📰"
        )

    fetched = data.get("fetched_at", "—")
    st.caption(
        f"⏰ KPIs use live APIs, cached up to 24h. **Last recomputed:** {fetched}. "
        "OpenFDA total = records in `drugsfda` (not a custom curated count). "
        "News figure = articles returned in one request (max 100), not global volume."
    )
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Charts ────────────────────────────────────────────────────────────────
    st.markdown("### 📈 Trends & Insights")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Clinical Trials by Phase (Recruiting)")
        with st.spinner("Loading phase data..."):
            phase_raw = fetch_trials_by_phase()
        phase_fetched = phase_raw.get("fetched_at")
        phase_data = {k: v for k, v in phase_raw.items() if k != "fetched_at"}

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
            st.caption(
                "ℹ️ Phase distribution from the **most recent 1,000 recruiting** trials returned by ClinicalTrials.gov "
                f"(not all trials worldwide). Recomputed: **{phase_fetched or '—'}**."
            )
        else:
            st.info("Phase data unavailable — ClinicalTrials.gov API may be temporarily slow.")

    with col2:
        st.markdown("#### Monthly FDA Drug Approvals (Last 6 Months)")
        with st.spinner("Loading FDA approvals..."):
            fda_data = fetch_monthly_fda_approvals()

        months = fda_data.get("months", [])
        approvals = fda_data.get("approvals", [])
        fda_fetched = fda_data.get("fetched_at")
        fda_n = fda_data.get("sample_size", 1000)

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
        st.caption(
            f"ℹ️ Counts **original NDA/BLA approvals** (`ORIG` + `AP`) whose status date falls in each month, "
            f"among the **{fda_n} most recent** `drugsfda` applications returned by OpenFDA — so months can look sparse; "
            f"this is a **sample-based estimate**, not FDA’s full approval ledger. Recomputed: **{fda_fetched or '—'}**."
        )

    # ── Therapeutic Areas ─────────────────────────────────────────────────────
    st.markdown("### 🎯 Top Therapeutic Areas")

    with st.spinner("Loading therapeutic area data..."):
        ta_data = fetch_therapeutic_area_data()

    ta_fetched = ta_data.get("fetched_at")
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
        st.caption(
            "ℹ️ **Categories** (Oncology, Cardiology, …) are fixed labels for comparison; **counts** are live "
            f"ClinicalTrials.gov recruiting totals and PubMed YTD hits per label. Recomputed: **{ta_fetched or '—'}**."
        )

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

    # ── RAG Operations (hidden by default) ────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("🧪 RAG Benchmark + Quality Gate (click to open)", expanded=False):
        st.markdown("### 🧪 RAG Benchmark Snapshot")
        st.caption("Run retrieval/generation timing tests and store JSON artifacts for manager reporting.")

        c1, c2 = st.columns([2, 1])
        with c1:
            include_gen = st.checkbox("Include generation timing", value=True, key="bench_include_gen")
        with c2:
            if st.button("▶️ Run Benchmark Suite", use_container_width=True):
                with st.spinner("Running benchmark suite..."):
                    rep = run_benchmark_suite(include_generation=include_gen, output_dir=config.BENCHMARK_OUTPUT_DIR)
                st.success(f"Benchmark completed: {rep.get('report_file', '-')}")
                st.rerun()

        bench_dir = Path(config.BENCHMARK_OUTPUT_DIR)
        if bench_dir.exists():
            reports = sorted(bench_dir.glob("benchmark_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if reports:
                latest = reports[0]
                try:
                    payload = json.loads(latest.read_text(encoding="utf-8"))
                    b1, b2, b3, b4 = st.columns(4)
                    b1.metric("Docs", str(payload.get("documents", 0)))
                    b2.metric("Chunks", str(payload.get("total_chunks", 0)))
                    b3.metric("Retrieval avg", f"{payload.get('retrieval_avg_ms', 0)} ms")
                    b4.metric("Retrieval p95", f"{payload.get('retrieval_p95_ms', 0)} ms")
                    st.caption(f"Latest report: {latest}")
                    csv_path = payload.get("csv_file")
                    csv_file = Path(csv_path).expanduser() if csv_path else None
                    if csv_path:
                        st.caption(f"CSV artifact: {csv_path}")
                    with st.expander("📋 View benchmark samples", expanded=False):
                        raw_samples = payload.get("samples")
                        if raw_samples is None:
                            st.warning(
                                "This JSON has no **samples** field (older report or partial file). "
                                "Run **Run Benchmark Suite** again to write per-query rows."
                            )
                        else:
                            samples_parse_error = False
                            try:
                                sdf = pd.DataFrame(raw_samples)
                            except (ValueError, TypeError) as exc:
                                samples_parse_error = True
                                st.warning(f"Could not turn **samples** into a table ({exc}). Raw payload fragment:")
                                st.json(raw_samples if isinstance(raw_samples, (list, dict)) else {"value": str(raw_samples)})
                                sdf = pd.DataFrame()

                            if not samples_parse_error:
                                if sdf.empty and isinstance(raw_samples, list) and len(raw_samples) > 0:
                                    st.warning(
                                        "**samples** has entries but produced an empty table — unexpected shape."
                                    )
                                elif sdf.empty:
                                    st.info(
                                        "**samples** is empty — no rows were stored for each benchmark query. "
                                        "That can happen if the benchmark run failed partway through or the file was edited. "
                                        "Run the suite again."
                                    )
                                else:
                                    st.dataframe(sdf, use_container_width=True, hide_index=True)
                        if csv_file and csv_file.is_file():
                            st.download_button(
                                label="Download benchmark CSV",
                                data=csv_file.read_bytes(),
                                file_name=csv_file.name,
                                mime="text/csv",
                                key="download_bench_csv",
                            )
                except Exception:
                    st.info("Benchmark report exists but could not be parsed.")

        st.markdown("---")
        st.markdown("### ✅ Agentic RAG Quality Gate")
        st.caption(
            "Closed-loop learning snapshot using feedback + benchmark/case-eval thresholds. "
            "You need both **benchmark_*.json** (from the button above) and **case_eval_*.json**. "
            "Create the latter from a terminal: `python tests/case_study_eval.py` (writes under `data/benchmarks/`)."
        )

        q1, q2 = st.columns(2)
        with q1:
            if st.button("🧠 Build Feedback Tuning Report", use_container_width=True):
                rows = load_feedback()
                rep = build_report(rows)
                out = write_report(rep)
                st.success(f"Tuning report written: {out}")
                st.json(rep)
        with q2:
            if st.button("🔍 Evaluate Release Gate", use_container_width=True):
                latest_bench = None
                latest_eval = None
                if bench_dir.exists():
                    bfiles = sorted(bench_dir.glob("benchmark_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
                    efiles = sorted(bench_dir.glob("case_eval_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
                    latest_bench = bfiles[0] if bfiles else None
                    latest_eval = efiles[0] if efiles else None

                if not latest_bench or not latest_eval:
                    st.error("Run benchmark suite and case_study_eval first (artifacts missing).")
                else:
                    b = json.loads(latest_bench.read_text(encoding="utf-8"))
                    e = json.loads(latest_eval.read_text(encoding="utf-8"))
                    retrieval_p95 = float(b.get("retrieval_p95_ms", 0))
                    case_pass_rate = float(e.get("pass_rate", 0))
                    pass_case = case_pass_rate >= float(config.QUALITY_MIN_CASE_PASS_RATE)
                    pass_p95 = retrieval_p95 <= float(config.QUALITY_MAX_RETRIEVAL_P95_MS)
                    status = pass_case and pass_p95
                    if status:
                        st.success("Release gate PASSED.")
                    else:
                        st.error("Release gate FAILED.")
                    st.json(
                        {
                            "benchmark_file": str(latest_bench),
                            "case_eval_file": str(latest_eval),
                            "case_pass_rate": case_pass_rate,
                            "retrieval_p95_ms": retrieval_p95,
                            "thresholds": {
                                "QUALITY_MIN_CASE_PASS_RATE": float(config.QUALITY_MIN_CASE_PASS_RATE),
                                "QUALITY_MAX_RETRIEVAL_P95_MS": float(config.QUALITY_MAX_RETRIEVAL_P95_MS),
                            },
                            "status": "PASS" if status else "FAIL",
                        }
                    )
