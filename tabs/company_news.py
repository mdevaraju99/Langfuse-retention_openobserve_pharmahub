"""
Company News Page
"""
import streamlit as st
from utils.data_fetchers import fetch_company_news
from utils.pharma_guardrails import guardrail_enabled, filter_pharma_relevant_news
from components.cards import news_card
from utils.formatters import truncate_text
from datetime import datetime
import config


def show():
    st.markdown('<h2 class="gradient-header">🏢 Pharma Company News</h2>', unsafe_allow_html=True)
    st.markdown("Latest news from major pharmaceutical companies")

    companies = config.PHARMA_COMPANIES
    pending = st.session_state.pop("company_pending_select", None)
    default_index = companies.index(pending) if pending and pending in companies else 0
    
    # Company selector
    col1, col2 = st.columns([2, 1])
    
    with col1:
        selected_company = st.selectbox(
            "Select Company",
            options=companies,
            index=default_index,
            key="company_news_select",
        )
    
    with col2:
        page_size = st.selectbox(
            "Results",
            options=[5, 10, 15, 20],
            index=1,
            label_visibility="collapsed"
        )
    
    # Fetch company news
    with st.spinner(f"🔍 Fetching news for {selected_company}..."):
        articles = fetch_company_news(company=selected_company, page_size=page_size)

    raw_n = len(articles)
    articles = filter_pharma_relevant_news(articles)
    if guardrail_enabled() and raw_n and not articles:
        st.warning(
            f"No articles for **{selected_company}** matched the pharma relevance filter. "
            "Try another company or turn off **Pharma relevance (all modules)** in the sidebar."
        )
        return
    
    if not articles:
        st.warning(f"⚠️ No recent news found for {selected_company}. Try another company or check your API key.")
        st.info("""
        **Tip:** Get a free NewsAPI key at https://newsapi.org/register
        
        Then create a `.env` file with:
        ```
        NEWSAPI_KEY=your_key_here
        ```
        """)
        return
    
    note = " (pharma-filtered)" if guardrail_enabled() else ""
    st.success(f"✅ Found {len(articles)} articles about {selected_company}{note}")
    
    # Display articles
    for article in articles:
        title = article.get("title", "No title")
        description = article.get("description", "No description available")
        source = article.get("source", {}).get("name", "Unknown")
        published_at = article.get("publishedAt", "")
        url = article.get("url", "#")
        
        # Format date
        try:
            date_obj = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
            formatted_date = date_obj.strftime("%B %d, %Y")
        except:
            formatted_date = published_at
        
        # Truncate description
        description = truncate_text(description, 200)
        
        news_card(
            title=title,
            description=description,
            source=source,
            date=formatted_date,
            url=url
        )
    
    # Quick company buttons
    st.markdown("### 🔗 Quick Access")
    top_companies = [c for c in config.COMPANY_NEWS_QUICK_ACCESS if c in companies] or companies[:6]
    cols = st.columns(3)
    for idx, company in enumerate(top_companies):
        with cols[idx % 3]:
            if st.button(company, key=f"btn_{company}", use_container_width=True, disabled=(company == selected_company)):
                st.session_state.company_pending_select = company
                st.rerun()
    
    # Refresh button
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Refresh News", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
