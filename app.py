"""
Pharma Knowledge Hub - Main Application
A comprehensive pharmaceutical knowledge portal with real-time data
"""
import streamlit as st
from streamlit_option_menu import option_menu
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import config

# Page configuration
st.set_page_config(
    page_title=config.APP_TITLE,
    page_icon=config.APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if "theme" not in st.session_state:
    st.session_state.theme = config.DEFAULT_THEME

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Load custom CSS with theme
def load_css(theme):
    css_path = project_root / "styles" / "custom.css"
    if css_path.exists():
        with open(css_path) as f:
            css_content = f.read()
        
        # Apply theme-specific overrides
        if theme == "light":
            theme_override = """
            :root {
                --bg-primary: #F3F5F9;
                --bg-secondary: #FFFFFF;
                --bg-card: #FFFFFF;
                --text-primary: #111827;
                --text-secondary: #4B5563;
                --border-color: rgba(15, 23, 42, 0.12);
                --shadow: rgba(15, 23, 42, 0.08);
                --hero-bg:
                    radial-gradient(950px 280px at 10% 0%, rgba(168, 85, 247, 0.20), transparent 58%),
                    radial-gradient(780px 260px at 92% 100%, rgba(14, 165, 233, 0.18), transparent 62%),
                    linear-gradient(135deg, rgba(129, 140, 248, 0.18), rgba(186, 230, 253, 0.24));
                --hero-border: rgba(99, 102, 241, 0.22);
                --hero-title: linear-gradient(135deg, #4F46E5 0%, #0EA5E9 100%);
                --hero-subtitle-color: #1F2937;
                --hero-pill-bg: rgba(79, 70, 229, 0.10);
                --hero-pill-border: rgba(79, 70, 229, 0.26);
                --hero-pill-text: #1F2937;
            }
            .main, [data-testid="stAppViewContainer"] {
                background-color: #F3F5F9 !important;
                color: #1F2937 !important;
            }
            [data-testid="stSidebar"] {
                background-color: #FFFFFF !important;
            }
            .stMarkdown, p, span, div {
                color: #1F2937 !important;
            }
            """
            css_content += theme_override
        else:
            theme_override = """
            :root {
                --bg-primary: #0B1120;
                --bg-secondary: #111827;
                --bg-card: #141C2F;
                --text-primary: #E5E7EB;
                --text-secondary: #9CA3AF;
                --border-color: rgba(148, 163, 184, 0.20);
                --shadow: rgba(0, 0, 0, 0.34);
                --hero-bg:
                    radial-gradient(1000px 300px at 10% 0%, rgba(139, 92, 246, 0.30), transparent 60%),
                    radial-gradient(820px 240px at 90% 100%, rgba(34, 211, 238, 0.22), transparent 60%),
                    linear-gradient(135deg, rgba(99, 102, 241, 0.20), rgba(30, 41, 59, 0.35));
                --hero-border: rgba(196, 181, 253, 0.28);
                --hero-title: linear-gradient(135deg, #C4B5FD 0%, #A5F3FC 100%);
                --hero-subtitle-color: #D1D5DB;
                --hero-pill-bg: rgba(255, 255, 255, 0.08);
                --hero-pill-border: rgba(255, 255, 255, 0.22);
                --hero-pill-text: #F3F4F6;
            }
            .main, [data-testid="stAppViewContainer"] {
                background-color: #0B1120 !important;
                color: #E5E7EB !important;
            }
            [data-testid="stSidebar"] {
                background-color: #111827 !important;
            }
            """
            css_content += theme_override
        
        st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)

load_css(st.session_state.theme)

# Hero header
st.markdown(
    f"""
<div class="app-hero">
    <div class="hero-tag">CROMO • RESEARCH</div>
    <h1 class="hero-title">{config.APP_ICON} {config.APP_TITLE}</h1>
    <p class="hero-subtitle">
        Explore real-time pharma intelligence across news, research, trials, regulations, events, and AI assistants.
    </p>
    <div class="hero-kpis">
        <span class="hero-pill">10+ Modules</span>
        <span class="hero-pill">Live APIs</span>
        <span class="hero-pill">Agentic RAG Ready</span>
    </div>
</div>
""",
    unsafe_allow_html=True,
)

# Sidebar
with st.sidebar:
    # Theme toggle at the top
    st.markdown("### ⚙️ Theme")
    
    theme_col1, theme_col2 = st.columns(2)
    with theme_col1:
        if st.button("🌙 Dark", use_container_width=True, type="primary" if st.session_state.theme == "dark" else "secondary"):
            st.session_state.theme = "dark"
            st.rerun()
    
    with theme_col2:
        if st.button("☀️ Light", use_container_width=True, type="primary" if st.session_state.theme == "light" else "secondary"):
            st.session_state.theme = "light"
            st.rerun()
    
    st.markdown("---")
    
    # Navigation menu
    st.markdown("### 📋 Navigation")
    
    selected = option_menu(
        menu_title=None,
        options=[
            "Pharma News",
            "Research Papers",
            "Analytics",
            "Drug Info",
            "Clinical Trials",
            "Regulatory",
            "Company News",
            "Events",
            "Case Studies",
            "Company Knowledge",
            "Chatbot"
        ],
        icons=[
            "newspaper",
            "journal-medical",
            "bar-chart-line",
            "capsule",
            "clipboard2-pulse",
            "shield-check",
            "building",
            "calendar-event",
            "book",
            "building-check",
            "chat-dots"
        ],
        menu_icon="cast",
        default_index=0,
        styles={
            "container": {
                "padding": "0.25rem 0 !important",
                "background-color": "transparent",
            },
            "icon": {"font-size": "0.95rem"},
            "nav-link": {
                "font-size": "0.95rem",
                "text-align": "left",
                "margin": "0.2rem 0",
                "padding": "0.62rem 0.9rem",
                "border-radius": "12px",
            },
            "nav-link-selected": {
                "background": "linear-gradient(135deg, #6366F1, #8B5CF6)",
                "font-weight": "600",
            },
        }
    )

# Route to tabs (renamed from pages to avoid Streamlit auto-detection)
if selected == "Pharma News":
    from tabs import pharma_news
    pharma_news.show()
    
elif selected == "Research Papers":
    from tabs import research_papers
    research_papers.show()
    
elif selected == "Analytics":
    from tabs import analytics
    analytics.show()
    
elif selected == "Drug Info":
    from tabs import drug_info
    drug_info.show()
    
elif selected == "Clinical Trials":
    from tabs import clinical_trials
    clinical_trials.show()
    
elif selected == "Regulatory":
    from tabs import regulatory
    regulatory.show()
    
elif selected == "Company News":
    from tabs import company_news
    company_news.show()
    
elif selected == "Events":
    from tabs import events
    events.show()

elif selected == "Case Studies":
    from tabs import case_studies
    case_studies.show()

elif selected == "Company Knowledge":
    from tabs import company_knowledge
    company_knowledge.show()
    
elif selected == "Chatbot":
    from tabs import chatbot
    chatbot.show()

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: var(--text-secondary); font-size: 0.85rem; padding: 1rem 0;">
    <p>
        Powered by NewsAPI, OpenFDA, ClinicalTrials.gov, PubMed & Groq AI<br>
        <em>Data is for informational purposes only. Always consult healthcare professionals.</em>
    </p>
</div>
""", unsafe_allow_html=True)
