"""
Company News Page
"""
import streamlit as st
from utils.data_fetchers import fetch_company_news
from components.cards import news_card
from utils.formatters import truncate_text
from datetime import datetime
import config


def show():
    st.markdown('<h2 class="gradient-header">🏢 Pharma Company News</h2>', unsafe_allow_html=True)
    st.markdown("Latest news from major pharmaceutical companies")
    
    # Company selector
    col1, col2 = st.columns([2, 1])
    
    with col1:
        selected_company = st.selectbox(
            "Select Company",
            options=config.PHARMA_COMPANIES,
            index=0
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
    
    st.success(f"✅ Found {len(articles)} articles about {selected_company}")
    
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
    top_companies = ["Pfizer", "Moderna", "Johnson & Johnson", "AstraZeneca", "Dr. Reddy's Laboratories", "Sun Pharma"]
    cols = st.columns(3)
    for idx, company in enumerate(top_companies):
        with cols[idx % 3]:
            if st.button(company, key=f"btn_{company}", use_container_width=True, disabled=(company == selected_company)):
                st.session_state.selected_company = company
                st.rerun()
    
    # Refresh button
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Refresh News", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
