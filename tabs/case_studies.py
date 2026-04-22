"""
Curated real-world pharma case studies mapping topics to Hub features.
Educational / demo content — not clinical advice.
"""
import streamlit as st


def show():
    st.markdown(
        '<h2 class="gradient-header">📖 Case Studies & Topic Hub</h2>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Use these **real, well-documented** industry cases to navigate the portal. "
        "Each section links **what to open in the Hub** and **what to try**."
    )

    st.info(
        "**Disclaimer:** Summaries are for learning and product demonstration only. "
        "Always verify facts in primary sources (labels, FDA, trial registries, peer-reviewed literature)."
    )

    cases = [
        {
            "title": "Aducanumab (Aduhelm) — accelerated approval & controversy",
            "summary": (
                "Illustrates **accelerated approval**, **surrogate endpoints**, **confirmatory trials**, "
                "and **post-market evidence** debates in Alzheimer’s disease."
            ),
            "hub": [
                "**Drug Info** — search *aducanumab* or *Aduhelm* for label-derived fields (when present in OpenFDA).",
                "**Research Papers** — search *aducanumab amyloid Alzheimer* for PubMed discourse.",
                "**Regulatory** — browse recalls/enforcement separately; for approvals narrative use **Research Papers** + **Pharma News**.",
                "**Pharma News** — track policy and payer coverage keywords.",
            ],
            "try": "Compare what the label emphasizes vs what trials discuss in PubMed abstracts.",
        },
        {
            "title": "Remdesivir (Veklury) — antiviral authorization pathways",
            "summary": (
                "Shows **EUAs**, **full approval**, and how **trial endpoints** (time to recovery, etc.) "
                "were discussed during a pandemic rollout."
            ),
            "hub": [
                "**Drug Info** — *remdesivir* or *Veklury*.",
                "**Clinical Trials** — search *remdesivir COVID* for active/completed studies.",
                "**Research Papers** — *remdesivir randomized controlled trial*.",
            ],
            "try": "Cross-check a trial’s **phase/status** in Clinical Trials with narrative in PubMed.",
        },
        {
            "title": "Semaglutide (Ozempic / Wegovy) — obesity & cardiometabolic outcomes",
            "summary": (
                "Useful for **indication expansion**, **cardiovascular outcomes trials**, and **real-world attention** in news."
            ),
            "hub": [
                "**Drug Info** — *semaglutide*.",
                "**Clinical Trials** — *semaglutide cardiovascular* or *STEP trial semaglutide*.",
                "**Company News** — large manufacturers publishing outcomes and access stories.",
            ],
            "try": "Use **Analytics** recruiting-phase snapshot as context, then deep-dive one drug in **Drug Info**.",
        },
        {
            "title": "PD-1 inhibitors (e.g., pembrolizumab) — oncology trial design patterns",
            "summary": (
                "Great for teaching **endpoint hierarchies**, **biomarker-enriched designs**, and **label evolution**."
            ),
            "hub": [
                "**Clinical Trials** — *pembrolizumab lung cancer*.",
                "**Research Papers** — *pembrolizumab overall survival*.",
                "**Drug Info** — *pembrolizumab*.",
            ],
            "try": "Pick one trial ID from Clinical Trials and search it in **Research Papers** as *NCT01234567* style queries.",
        },
        {
            "title": "Gene therapies — rare disease, durability, and regulatory scrutiny",
            "summary": (
                "Highlights **long follow-up**, **small populations**, and **safety signal** tracking."
            ),
            "hub": [
                "**Clinical Trials** — *gene therapy hemophilia* (example condition).",
                "**Pharma News** — *gene therapy FDA*.",
                "**Regulatory** — enforcement patterns (manufacturing quality, recalls).",
            ],
            "try": "Contrast **trial inclusion criteria** (Clinical Trials) with **warnings** themes (Drug Info) where available.",
        },
    ]

    for i, c in enumerate(cases):
        with st.expander(f"**{i + 1}. {c['title']}**", expanded=(i == 0)):
            st.markdown(c["summary"])
            st.markdown("**Where to go in this Hub**")
            for line in c["hub"]:
                st.markdown(f"- {line}")
            st.markdown("**Suggested exercise**")
            st.markdown(f"- {c['try']}")

    st.markdown("---")
    st.markdown("### How this ties to new Hub capabilities")
    st.markdown(
        """
- **Company Knowledge (RAG)** — upload *your* protocol, CSR excerpt, or SOP PDFs; ask cross-document questions.
- **Agentic RAG** — optional *rewrite → retrieve → relevance gate → answer* path for more reliable grounding.
- **Streaming** — answers render token-by-token for a more interactive feel.
- **Richer PDF ingestion** — PyMuPDF path improves layout fidelity and attempts **table capture** into text/markdown blocks.
- **Scalability controls** — ingestion respects configured **page/character/chunk** ceilings (see `config.py` / sidebar in Company Knowledge).
        """
    )
