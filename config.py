"""
Configuration settings for Pharma Knowledge Hub
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Endpoints
NEWSAPI_ENDPOINT = "https://newsapi.org/v2/everything"
OPENFDA_BASE = "https://api.fda.gov/drug"
CLINICALTRIALS_ENDPOINT = "https://clinicaltrials.gov/api/v2/studies"
PUBMED_SEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_SUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

# API Keys (optional for most APIs)
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")
OPENFDA_KEY = os.getenv("OPENFDA_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Neo4j Configuration
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")

# Cache settings (in seconds)
CACHE_TTL = {
    "news": 3600,           # 1 hour
    "drug_info": 86400,     # 24 hours
    "clinical_trials": 21600,  # 6 hours
    "research": 7200,       # 2 hours
    "analytics": 86400,     # 24 hours
    "events": 604800        # 1 week
}

# Rate limiting
REQUEST_TIMEOUT = 10  # seconds
MAX_RETRIES = 3

# UI Settings
APP_TITLE = "Pharma Knowledge Hub"
APP_ICON = "💊"
DEFAULT_THEME = "dark"

# Pharma companies for company news
PHARMA_COMPANIES = [
    "Pfizer", "Moderna", "Johnson & Johnson", "AstraZeneca",
    "Novartis", "Roche", "Merck", "GSK", "Sanofi", "AbbVie",
    "Bristol Myers Squibb", "Eli Lilly", "Gilead Sciences",
    "Amgen", "Biogen", "Regeneron", "Dr. Reddy's Laboratories",
    "Sun Pharma", "Cipla", "Lupin", "Zydus Lifesciences", "Takeda"
]

# Major pharma news sources
PHARMA_NEWS_SOURCES = [
    "reuters.com",
    "bloomberg.com",
    "fiercepharma.com",
    "biopharmadive.com",
    "endpoints.com"
]
