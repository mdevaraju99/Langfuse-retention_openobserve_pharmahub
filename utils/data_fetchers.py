"""
Data fetchers for various pharma APIs
"""
import streamlit as st
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from utils.api_client import APIClient
import config


@st.cache_data(ttl=config.CACHE_TTL["news"])
def fetch_pharma_news(query: str = "pharmaceutical", page_size: int = 10) -> List[Dict[str, Any]]:
    """Fetch pharma news from NewsAPI"""
    params = {
        "q": query,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": page_size,
        "apiKey": config.NEWSAPI_KEY if config.NEWSAPI_KEY else "demo"
    }
    
    # Add date filter (last 30 days)
    date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    
    response = APIClient.make_request(config.NEWSAPI_ENDPOINT, params=params)
    
    if response and response.get("status") == "ok":
        return response.get("articles", [])

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
def fetch_research_papers(query: str = "pharmaceutical", max_results: int = 10) -> List[Dict[str, Any]]:
    """Fetch research papers from PubMed"""
    # Step 1: Search for IDs
    search_params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
        "sort": "relevance"
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
def fetch_clinical_trials(query: str = "diabetes", page_size: int = 10) -> List[Dict[str, Any]]:
    """Fetch clinical trials from ClinicalTrials.gov API v2"""
    params = {
        "query.term": query,
        "pageSize": page_size,
        "format": "json"
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
    """Fetch data for analytics dashboard"""
    # Get counts from various APIs
    
    # Total drugs from FDA
    drug_count_params = {"limit": 1}
    if config.OPENFDA_KEY:
        drug_count_params["api_key"] = config.OPENFDA_KEY
    drug_response = APIClient.make_request(
        f"{config.OPENFDA_BASE}/drugsfda.json",
        params=drug_count_params
    )
    total_drugs = drug_response.get("meta", {}).get("results", {}).get("total", 0) if drug_response else 0
    
    # Active trials
    trials_response = APIClient.make_request(
        config.CLINICALTRIALS_ENDPOINT,
        params={"query.term": "recruiting", "pageSize": 1, "format": "json"}
    )
    active_trials = trials_response.get("totalCount", 0) if trials_response else 0
    
    # Recent papers (this month)
    date_filter = datetime.now().strftime("%Y/%m/01")
    papers_params = {
        "db": "pubmed",
        "term": f"pharmaceutical AND {date_filter}[PDAT]",
        "retmode": "json"
    }
    papers_response = APIClient.make_request(config.PUBMED_SEARCH, params=papers_params)
    recent_papers = int(papers_response.get("esearchresult", {}).get("count", 0)) if papers_response else 0
    
    return {
        "total_drugs": total_drugs,
        "active_trials": active_trials,
        "recent_papers": recent_papers,
        "news_count": len(fetch_pharma_news(page_size=100))  # Cached
    }
