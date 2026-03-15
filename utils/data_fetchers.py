"""
Data fetchers for various pharma APIs
"""
import streamlit as st
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from utils.api_client import APIClient
import config


@st.cache_data(ttl=config.CACHE_TTL["news"])
def fetch_pharma_news(query: str = "pharmaceutical", page_size: int = 100) -> List[Dict[str, Any]]:
    """Fetch pharma news from NewsAPI (free tier – no pagination/date filter).
    Fetches a large batch so the UI can rotate through different subsets on refresh.
    """
    params = {
        "q": query,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": min(page_size, 100),  # NewsAPI free tier max is 100
        "apiKey": config.NEWSAPI_KEY if config.NEWSAPI_KEY else "demo"
    }

    response = APIClient.make_request(config.NEWSAPI_ENDPOINT, params=params)

    if response and response.get("status") == "ok":
        return response.get("articles", [])
    return []

@st.cache_data(ttl=config.CACHE_TTL["news"])
def fetch_pharma_news_multi_query(base_query: str, page_size: int = 50) -> List[Dict[str, Any]]:
    """
    Enhanced news fetcher. 
    Instead of making multiple API calls (which hits rate limits), 
    we fetch a larger batch with a broad query and filter locally.
    """
    try:
        # Fetch a single large batch
        return fetch_pharma_news(query=base_query, page_size=page_size)
    except Exception:
        return []



@st.cache_data(ttl=config.CACHE_TTL["research"])
def fetch_research_papers(query: str = "pharmaceutical", max_results: int = 10, page: int = 1) -> List[Dict[str, Any]]:
    """Fetch research papers from PubMed with pagination support (PubMed is free, supports retstart offset)."""
    # Step 1: Search for IDs
    retstart = (page - 1) * max_results
    search_params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retstart": retstart,
        "retmode": "json",
        "sort": "most_recent"
    }
    
    search_response = APIClient.make_request(config.PUBMED_SEARCH, params=search_params)
    
    if not search_response or "esearchresult" not in search_response:
        return []
    
    id_list = search_response["esearchresult"].get("idlist", [])
    
    if not id_list:
        return []
    
    # Step 2: Get summaries
    summary_params = {
        "db": "pubmed",
        "id": ",".join(id_list),
        "retmode": "json"
    }
    
    summary_response = APIClient.make_request(config.PUBMED_SUMMARY, params=summary_params)
    
    if not summary_response or "result" not in summary_response:
        return []
    
    papers = []
    for paper_id in id_list:
        if paper_id in summary_response["result"]:
            paper_data = summary_response["result"][paper_id]
            papers.append({
                "id": paper_id,
                "title": paper_data.get("title", "N/A"),
                "authors": [author.get("name", "") for author in paper_data.get("authors", [])],
                "journal": paper_data.get("fulljournalname", "N/A"),
                "date": paper_data.get("pubdate", "N/A"),
                "doi": paper_data.get("elocationid", ""),
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{paper_id}/"
            })
    
    return papers


@st.cache_data(ttl=config.CACHE_TTL["drug_info"])
def fetch_drug_info(drug_name: str) -> List[Dict[str, Any]]:
    """Fetch drug information from OpenFDA"""
    endpoint = f"{config.OPENFDA_BASE}/label.json"
    
    params = {
        "search": f'openfda.brand_name:"{drug_name}" OR openfda.generic_name:"{drug_name}"',
        "limit": 5
    }
    
    if config.OPENFDA_KEY:
        params["api_key"] = config.OPENFDA_KEY
    
    response = APIClient.make_request(endpoint, params=params)
    
    if response and "results" in response:
        drugs = []
        for result in response["results"]:
            openfda = result.get("openfda", {})
            drugs.append({
                "brand_name": openfda.get("brand_name", ["N/A"])[0] if openfda.get("brand_name") else "N/A",
                "generic_name": openfda.get("generic_name", ["N/A"])[0] if openfda.get("generic_name") else "N/A",
                "manufacturer": openfda.get("manufacturer_name", ["N/A"])[0] if openfda.get("manufacturer_name") else "N/A",
                "purpose": result.get("purpose", ["N/A"])[0] if result.get("purpose") else "N/A",
                "indications": result.get("indications_and_usage", ["N/A"])[0] if result.get("indications_and_usage") else "N/A",
                "warnings": result.get("warnings", ["N/A"])[0] if result.get("warnings") else "N/A",
                "route": openfda.get("route", ["N/A"])[0] if openfda.get("route") else "N/A"
            })
        return drugs
    return []


@st.cache_data(ttl=config.CACHE_TTL["clinical_trials"])
def fetch_clinical_trials(query: str = "diabetes", page_size: int = 100) -> List[Dict[str, Any]]:
    """Fetch clinical trials from ClinicalTrials.gov API v2 with support for larger batches for rotation"""
    params = {
        "query.term": query,
        "pageSize": min(page_size, 100),
        "format": "json",
        "countTotal": "true"
    }
    
    response = APIClient.make_request(config.CLINICALTRIALS_ENDPOINT, params=params)
    
    if response and "studies" in response:
        trials = []
        for study in response["studies"]:
            protocol = study.get("protocolSection", {})
            identification = protocol.get("identificationModule", {})
            status = protocol.get("statusModule", {})
            design = protocol.get("designModule", {})
            
            trials.append({
                "nct_id": identification.get("nctId", "N/A"),
                "title": identification.get("briefTitle", "N/A"),
                "status": status.get("overallStatus", "N/A"),
                "phase": design.get("phases", ["N/A"])[0] if design.get("phases") else "N/A",
                "enrollment": status.get("enrollmentInfo", {}).get("count", "N/A"),
                "url": f"https://clinicaltrials.gov/study/{identification.get('nctId', '')}"
            })
        return trials
    return []


@st.cache_data(ttl=config.CACHE_TTL["news"])
def fetch_regulatory_updates(limit: int = 10) -> List[Dict[str, Any]]:
    """Fetch FDA enforcement/recall data"""
    endpoint = f"{config.OPENFDA_BASE}/enforcement.json"
    
    params = {
        "limit": limit,
        "sort": "report_date:desc"
    }
    
    if config.OPENFDA_KEY:
        params["api_key"] = config.OPENFDA_KEY
    
    response = APIClient.make_request(endpoint, params=params)
    
    if response and "results" in response:
        updates = []
        for result in response["results"]:
            updates.append({
                "product": result.get("product_description", "N/A"),
                "reason": result.get("reason_for_recall", "N/A"),
                "classification": result.get("classification", "N/A"),
                "date": result.get("report_date", "N/A"),
                "company": result.get("recalling_firm", "N/A"),
                "status": result.get("status", "N/A")
            })
        return updates
    return []


@st.cache_data(ttl=config.CACHE_TTL["news"])
def fetch_company_news(company: str, page_size: int = 5) -> List[Dict[str, Any]]:
    """Fetch news for specific pharma company"""
    return fetch_pharma_news(query=f"{company} pharma pharmaceutical", page_size=page_size)



@st.cache_data(ttl=config.CACHE_TTL["analytics"])
def fetch_analytics_data() -> Dict[str, Any]:
    """Fetch live KPI data for analytics dashboard. Cached 24 hours."""

    # ── 1. Total FDA-approved drugs ─────────────────────────────────────────
    drug_count_params = {"limit": 1}
    if config.OPENFDA_KEY:
        drug_count_params["api_key"] = config.OPENFDA_KEY
    drug_response = APIClient.make_request(
        f"{config.OPENFDA_BASE}/drugsfda.json",
        params=drug_count_params
    )
    total_drugs = (
        drug_response.get("meta", {}).get("results", {}).get("total", 0)
        if drug_response else 0
    )

    # ── 2. Active (RECRUITING) clinical trials ───────────────────────────────
    # NOTE: Do NOT include 'fields' param — it suppresses totalCount in the response.
    trials_response = APIClient.make_request(
        config.CLINICALTRIALS_ENDPOINT,
        params={
            "filter.overallStatus": "RECRUITING",
            "pageSize": 1,
            "format": "json",
            "countTotal": "true",
            "query.term": "drug OR pharmaceutical"
        }
    )
    active_trials = trials_response.get("totalCount", 0) if trials_response else 0

    # ── 3. Research papers published this month (PubMed) ────────────────────
    date_filter = datetime.now().strftime("%Y/%m/01")
    papers_params = {
        "db": "pubmed",
        "term": f"pharmaceutical[MeSH] AND {date_filter}[PDAT]",
        "retmode": "json",
        "retmax": 0
    }
    papers_response = APIClient.make_request(config.PUBMED_SEARCH, params=papers_params)
    recent_papers = (
        int(papers_response.get("esearchresult", {}).get("count", 0))
        if papers_response else 0
    )

    # ── 4. News articles fetched ─────────────────────────────────────────────
    news_articles = fetch_pharma_news(page_size=100)
    news_count = len(news_articles) if news_articles else 0

    return {
        "total_drugs": total_drugs,
        "active_trials": active_trials,
        "recent_papers": recent_papers,
        "news_count": news_count,
    }


@st.cache_data(ttl=config.CACHE_TTL["analytics"])
def fetch_trials_by_phase() -> Dict[str, int]:
    """
    Get phase distribution of RECRUITING trials.
    'filter.phase' is NOT a valid ClinicalTrials.gov v2 parameter (causes 400).
    Strategy: fetch 1000 recruiting trials, count phases from the returned data.
    This gives a real distribution sample of active trials.
    """
    resp = APIClient.make_request(
        config.CLINICALTRIALS_ENDPOINT,
        params={
            "filter.overallStatus": "RECRUITING",
            "pageSize": 1000,
            "format": "json",
            "countTotal": "true"
        }
    )

    counts = {"Phase 1": 0, "Phase 2": 0, "Phase 3": 0, "Phase 4": 0, "Other/NA": 0}

    if resp and "studies" in resp:
        for study in resp["studies"]:
            protocol = study.get("protocolSection", {})
            design = protocol.get("designModule", {})
            phases = design.get("phases", [])
            matched = False
            for phase in phases:
                p = phase.upper().replace(" ", "")
                if "PHASE1" in p or "EARLYPHASE1" in p:
                    counts["Phase 1"] += 1
                    matched = True
                elif "PHASE2" in p:
                    counts["Phase 2"] += 1
                    matched = True
                elif "PHASE3" in p:
                    counts["Phase 3"] += 1
                    matched = True
                elif "PHASE4" in p:
                    counts["Phase 4"] += 1
                    matched = True
            if not matched:
                counts["Other/NA"] += 1

    # Remove zero-count Other/NA to keep chart clean
    if counts.get("Other/NA", 0) == 0:
        counts.pop("Other/NA", None)

    return counts


@st.cache_data(ttl=config.CACHE_TTL["analytics"])
def fetch_therapeutic_area_data() -> Dict[str, Any]:
    """
    Fetch active trial counts and paper counts per therapeutic area. Cached 24 hours.
    NOTE: Do NOT include 'fields' param in ClinicalTrials query — it suppresses totalCount.
    """
    areas = ["Oncology", "Cardiology", "Neurology", "Immunology", "Infectious Disease"]
    trial_counts = []
    paper_counts = []

    for area in areas:
        # ClinicalTrials: search by condition, filter RECRUITING
        resp = APIClient.make_request(
            config.CLINICALTRIALS_ENDPOINT,
            params={
                "query.cond": area,
                "filter.overallStatus": "RECRUITING",
                "pageSize": 1,
                "format": "json",
                "countTotal": "true"
            }
        )
        trial_counts.append(resp.get("totalCount", 0) if resp else 0)

        # PubMed: papers published this year for this disease area
        year_from = datetime.now().strftime("%Y/01/01")
        p_resp = APIClient.make_request(
            config.PUBMED_SEARCH,
            params={
                "db": "pubmed",
                "term": f"{area} AND {year_from}[PDAT]",
                "retmode": "json",
                "retmax": 0
            }
        )
        paper_counts.append(
            int(p_resp.get("esearchresult", {}).get("count", 0)) if p_resp else 0
        )

    return {"areas": areas, "trial_counts": trial_counts, "paper_counts": paper_counts}


@st.cache_data(ttl=config.CACHE_TTL["analytics"])
def fetch_monthly_fda_approvals() -> Dict[str, Any]:
    """
    Fetch FDA drug approval counts for the last 6 months.
    Strategy: Fetch 200 most recent drug applications (simple query, no date range),
    then bucket submission dates by month in Python. Avoids broken date-range queries.
    """
    from datetime import date

    # Build last-6-month buckets (YYYYMM keys)
    today = date.today()
    month_buckets: Dict[str, Dict] = {}
    for i in range(5, -1, -1):
        month = (today.month - i - 1) % 12 + 1
        year = today.year - ((i + 12 - today.month) // 12)
        key = f"{year:04d}{month:02d}"
        label = date(year, month, 1).strftime("%b %Y")
        month_buckets[key] = {"label": label, "count": 0}

    # Fetch 200 most recent drug applications — simple query that always works
    params: Dict[str, Any] = {"limit": 200}
    if config.OPENFDA_KEY:
        params["api_key"] = config.OPENFDA_KEY

    resp = APIClient.make_request(f"{config.OPENFDA_BASE}/drugsfda.json", params=params)

    if resp and "results" in resp:
        for drug in resp["results"]:
            for submission in drug.get("submissions", []):
                # Count original NDA/BLA approvals only
                if (submission.get("submission_type") == "ORIG" and
                        submission.get("submission_status") == "AP"):
                    raw_date = submission.get("submission_status_date", "")
                    # OpenFDA date format: YYYYMMDD (8 chars, no hyphens)
                    if len(raw_date) >= 6:
                        month_key = raw_date[:6]  # e.g. "202503"
                        if month_key in month_buckets:
                            month_buckets[month_key]["count"] += 1

    months_labels = [v["label"] for v in month_buckets.values()]
    approval_counts = [v["count"] for v in month_buckets.values()]
    return {"months": months_labels, "approvals": approval_counts}
