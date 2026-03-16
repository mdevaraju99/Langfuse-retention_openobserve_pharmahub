"""
Events Page - Improved Dynamic Events with Multi-Source Fetching
"""
import streamlit as st
from utils.data_fetchers import fetch_pharma_news_multi_query
from components.cards import news_card
from datetime import datetime
from utils.formatters import truncate_text
import re

def extract_dates_from_text(text):
    """
    Extract potential event dates from text.
    Returns list of found dates and whether they're in the future.
    """
    text_lower = text.lower()
    
    # Pattern for dates like "March 15-17, 2026" or "November 2026"
    date_patterns = [
        r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}[-–]\d{1,2},?\s+202[6-9]',
        r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+202[6-9]',
        r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+202[6-9]',
        r'202[6-9]',  # Just year
        r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}[-–]\d{1,2},?\s+202[6-9]',
    ]
    
    found_dates = []
    for pattern in date_patterns:
        matches = re.findall(pattern, text_lower)
        found_dates.extend(matches)
    
    # Check if mentions future year
    has_future_year = any(str(year) in text for year in [2026, 2027, 2028])
    
    return found_dates, has_future_year

def smart_event_filter(articles, event_type="all", include_past=False):
    """
    Advanced filtering for actual events with multi-criteria scoring.
    
    event_type: "hackathon", "conference", "workshop", or "all"
    include_past: If True, also include recent past events
    """
    
    # Strong event indicators (high confidence these are actual events)
    strong_event_keywords = {
        "hackathon": [
            "hackathon", "hack-a-thon", "coding competition", "coding challenge",
            "innovation challenge", "dev challenge", "datathon"
        ],
        "conference": [
            "conference", "summit", "symposium", "congress", "expo", "forum",
            "annual meeting", "world congress", "international conference"
        ],
        "workshop": [
            "workshop", "webinar", "training session", "masterclass", "bootcamp",
            "short course", "hands-on training", "certification course"
        ]
    }
    
    # Action-oriented keywords (suggests it's an event you can attend/participate)
    action_keywords = [
        "register", "registration", "deadline", "apply", "submit", "join us",
        "attend", "participate", "enroll", "spots available", "virtual event",
        "in-person event", "hybrid event"
    ]
    
    # Date-related keywords (confirms it's scheduled)
    date_keywords = [
        "scheduled for", "taking place", "to be held", "dates announced", 
        "event date", "happening on", "2026", "2027"
    ]
    
    # EXCLUDE these - they're news, not events
    exclusion_keywords = [
        "market report", "market analysis", "stock", "shares", "earnings",
        "quarterly report", "revenue", "profit", "financial results",
        "crime", "police", "lawsuit", "litigation", "cagr", "forecast", 
        "market size", "merger", "acquisition", "dividend", "price target"
    ]
    
    # Pharma-specific keywords to ensure relevance
    pharma_keywords = [
        "pharmaceutical", "pharma", "biotech", "drug", "clinical", "fda", 
        "regulatory", "medicine", "therapy", "healthcare", "life sciences"
    ]
    
    scored_events = []
    current_date = datetime.now()
    
    for article in articles:
        title = article.get("title", "").lower()
        desc = (article.get("description", "") or "").lower()
        combined_text = f"{title} {desc}"
        
        # Initialize score
        score = 0
        event_metadata = {
            "is_future": False,
            "is_past": False,
            "has_dates": False,
            "is_actionable": False,
            "event_category": event_type
        }
        
        # 1. CHECK FOR EXCLUSIONS (immediate disqualification)
        if any(keyword in combined_text for keyword in exclusion_keywords):
            continue
        
        # 2. CHECK PHARMA RELEVANCE
        pharma_score = sum(1 for kw in pharma_keywords if kw in combined_text)
        if pharma_score == 0:
            continue  # Must be pharma-related
        score += pharma_score * 2
        
        # 3. CHECK EVENT TYPE MATCH
        if event_type != "all":
            type_match = sum(1 for kw in strong_event_keywords[event_type] if kw in combined_text)
            if type_match == 0:
                continue  # Must match the event type
            score += type_match * 10  # High weight
        else:
            # Check all types
            for evt_type, keywords in strong_event_keywords.items():
                type_match = sum(1 for kw in keywords if kw in combined_text)
                if type_match > 0:
                    score += type_match * 10
                    event_metadata["event_category"] = evt_type
                    break
        
        # 4. CHECK FOR ACTION KEYWORDS (suggests registration/participation)
        action_score = sum(1 for kw in action_keywords if kw in combined_text)
        if action_score > 0:
            score += action_score * 5
            event_metadata["is_actionable"] = True
        
        # 5. CHECK FOR DATE KEYWORDS
        date_score = sum(1 for kw in date_keywords if kw in combined_text)
        if date_score > 0:
            score += date_score * 3
            event_metadata["has_dates"] = True
        
        # 6. EXTRACT AND VALIDATE DATES
        found_dates, has_future_year = extract_dates_from_text(combined_text)
        if has_future_year:
            score += 15  # Strong signal
            event_metadata["is_future"] = True
        
        # 7. CHECK PUBLICATION DATE (recent articles more likely to be upcoming events)
        try:
            pub_date = datetime.fromisoformat(article.get("publishedAt", "").replace('Z', '+00:00'))
            days_old = (current_date - pub_date).days
            
            if days_old <= 7:
                score += 5  # Very recent
                if not has_future_year and days_old <= 3:
                    # Very recent article without future year might be a past event
                    event_metadata["is_past"] = True
            elif days_old <= 30:
                score += 2  # Recent
        except:
            pass
        
        # 8. MINIMUM SCORE THRESHOLD
        if score >= 15:  # Adjust threshold as needed
            article["_score"] = score
            article["_metadata"] = event_metadata
            scored_events.append(article)
    
    # Sort by score (highest first)
    scored_events.sort(key=lambda x: x["_score"], reverse=True)
    
    # Split into future and past
    future_events = [e for e in scored_events if e["_metadata"]["is_future"]]
    past_events = [e for e in scored_events if e["_metadata"]["is_past"] and include_past]
    
    return future_events, past_events

def show():
    st.markdown('<h2 class="gradient-header">📅 Pharma Events & Opportunities</h2>', unsafe_allow_html=True)
    st.markdown("🔴 **Live Feed** | Auto-filtered for quality | Updates every hour")
    
    # Refresh button
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    
    tab1, tab2, tab3 = st.tabs(["🏆 Hackathons", "🎤 Conferences", "🎓 Workshops"])
    

    # Helper function to fetch and display
    def fetch_and_display(query, event_type, tab_name, icon="📅"):
        all_articles = []
        
        with st.spinner(f"🔍 Searching global news for {tab_name}..."):
            # Single robust query fetch
            try:
                # Use a larger page size since we are doing one big query
                all_articles = fetch_pharma_news_multi_query(base_query=query, page_size=50)
            except Exception as e:
                st.error(f"Error fetching {tab_name}: {str(e)}")
                return
            
            # Remove duplicates based on URL
            seen_urls = set()
            unique_articles = []
            for article in all_articles:
                url = article.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_articles.append(article)
            
            # Apply smart filtering (Upcoming only)
            future_events, past_events = smart_event_filter(
                unique_articles, 
                event_type=event_type,
                include_past=False
            )
        
        # Display results
        if future_events:
            st.success(f"✅ Found {len(future_events)} upcoming {tab_name}")
            st.markdown(f"### 🔮 Upcoming {tab_name}")
            display_cards(future_events, icon)
        
        
        if not future_events and not past_events:
            st.warning(f"❌ No {tab_name} found in current news feed")
            st.markdown(f"""
            **Suggestions:**
            - Try refreshing later (news updates frequently)
            - Check dedicated platforms: [Devpost](https://devpost.com), [BioConferences](https://bioconferences.com)
            """)

    def display_cards(articles, icon):
        """Display article cards"""
        for article in articles[:10]:  # Limit to top 10
            title = article.get("title", "No title")
            description = article.get("description", "No description available")
            source = article.get("source", {}).get("name", "Unknown")
            published_at = article.get("publishedAt", "")
            url = article.get("url", "#")
            
            try:
                date_obj = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                formatted_date = date_obj.strftime("%B %d, %Y")
            except:
                formatted_date = published_at
            
            news_card(
                title=f"{icon} {title}",
                description=truncate_text(description, 250),
                source=source,
                date=f"Published: {formatted_date}",
                url=url
            )

    # TAB 1: HACKATHONS
    with tab1:
        st.markdown("### 💻 Pharma & Healthcare Hackathons")
        # Combined Master Query
        hackathon_query = '(hackathon OR "coding competition" OR "innovation challenge" OR datathon) AND ("pharmaceutical" OR "biotech" OR "healthcare" OR "drug discovery")'
        fetch_and_display(hackathon_query, "hackathon", "hackathons", "🚀")
    
    # TAB 2: CONFERENCES
    with tab2:
        st.markdown("### 🎤 Industry Conferences & Summits")
        # Combined Master Query
        conference_query = '(conference OR summit OR congress OR symposium) AND ("pharmaceutical" OR "biotech" OR "clinical trials") AND (2026 OR 2027)'
        fetch_and_display(conference_query, "conference", "conferences", "🗓️")
    
    # TAB 3: WORKSHOPS
    with tab3:
        st.markdown("### 🎓 Training, Workshops & Webinars")
        # Combined Master Query
        workshop_query = '(workshop OR webinar OR training OR "certification course") AND (FDA OR "regulatory affairs" OR "clinical trials" OR GMP)'
        fetch_and_display(workshop_query, "workshop", "workshops", "🎓")

