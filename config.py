"""
Configuration settings for Pharma Knowledge Hub
"""
import os

# Transformers: use PyTorch only (avoids optional TF/keras imports on Windows)
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_FLAX", "0")

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
# Must match CREATE VECTOR INDEX name in neo4j_manager.create_vector_index
NEO4J_VECTOR_INDEX_NAME = os.getenv("NEO4J_VECTOR_INDEX_NAME", "chunk_embeddings")

# RAG / ingestion limits (tune for memory and Neo4j capacity)
RAG_MAX_CHUNKS_PER_DOC = int(os.getenv("RAG_MAX_CHUNKS_PER_DOC", "400"))
RAG_MAX_INGEST_CHARS = int(os.getenv("RAG_MAX_INGEST_CHARS", str(2_000_000)))
RAG_MAX_PDF_MB = int(os.getenv("RAG_MAX_PDF_MB", "80"))
RAG_MAX_PDF_PAGES = int(os.getenv("RAG_MAX_PDF_PAGES", "250"))

# UI: stream LLM tokens where supported
ENABLE_STREAMING_UI = os.getenv("ENABLE_STREAMING_UI", "true").lower() in ("1", "true", "yes")
# Agentic RAG: rewrite + relevance gate + optional second retrieval
ENABLE_AGENTIC_RAG_DEFAULT = os.getenv("ENABLE_AGENTIC_RAG_DEFAULT", "true").lower() in ("1", "true", "yes")
ENABLE_ANSWER_VALIDATION = os.getenv("ENABLE_ANSWER_VALIDATION", "true").lower() in ("1", "true", "yes")
RAG_CONFIDENCE_THRESHOLD = int(os.getenv("RAG_CONFIDENCE_THRESHOLD", "55"))
RAG_STRICT_ABSTAIN_ON_FAIL = os.getenv("RAG_STRICT_ABSTAIN_ON_FAIL", "true").lower() in ("1", "true", "yes")
RAG_MAX_REVISION_ROUNDS = int(os.getenv("RAG_MAX_REVISION_ROUNDS", "1"))
RAG_CLARIFIER_MIN_CHARS = int(os.getenv("RAG_CLARIFIER_MIN_CHARS", "12"))
BENCHMARK_OUTPUT_DIR = os.getenv("BENCHMARK_OUTPUT_DIR", "data/benchmarks")

# Operational quality thresholds (release gate)
QUALITY_MIN_CASE_PASS_RATE = float(os.getenv("QUALITY_MIN_CASE_PASS_RATE", "0.70"))
QUALITY_MAX_RETRIEVAL_P95_MS = float(os.getenv("QUALITY_MAX_RETRIEVAL_P95_MS", "3000"))
QUALITY_MIN_VALIDATION_CONFIDENCE = int(os.getenv("QUALITY_MIN_VALIDATION_CONFIDENCE", "55"))

# Rich media extraction / preview storage
MEDIA_ASSETS_DIR = os.getenv("MEDIA_ASSETS_DIR", "data/media_assets")
RAG_MAX_MEDIA_IMAGES = int(os.getenv("RAG_MAX_MEDIA_IMAGES", "24"))
RAG_MAX_MEDIA_TABLE_PREVIEWS = int(os.getenv("RAG_MAX_MEDIA_TABLE_PREVIEWS", "12"))
RAG_MAX_MEDIA_SNIPPETS = int(os.getenv("RAG_MAX_MEDIA_SNIPPETS", "12"))

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
DEFAULT_THEME = "light"

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
