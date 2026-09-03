"""
Configuration settings for Pharma Knowledge Hub
"""
import os
import json

# Transformers: use PyTorch only (avoids optional TF/keras imports on Windows)
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_FLAX", "0")

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def _csv_env(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name, "")
    if not raw.strip():
        return list(default)
    return [x.strip() for x in raw.split(",") if x.strip()]


def _json_env(name: str, default):
    raw = os.getenv(name, "")
    if not raw.strip():
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default

# API Endpoints
NEWSAPI_ENDPOINT = "https://newsapi.org/v2/everything"
OPENFDA_BASE = "https://api.fda.gov/drug"
CLINICALTRIALS_ENDPOINT = "https://clinicaltrials.gov/api/v2/studies"
PUBMED_SEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_SUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

def _strip_env_quotes(value: str) -> str:
    s = (value or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1].strip()
    return s


# API Keys (optional for most APIs)
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")
OPENFDA_KEY = os.getenv("OPENFDA_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Groq chat models (OpenAI-compatible IDs). Llama defaults were retired for this POC.
GROQ_MODEL_PRIMARY = _strip_env_quotes(
    os.getenv("GROQ_MODEL_PRIMARY", "openai/gpt-oss-120b")
)
GROQ_MODEL_FAST = _strip_env_quotes(
    os.getenv("GROQ_MODEL_FAST", "openai/gpt-oss-20b")
)
# Lower primary temperature reduces GPT-style reasoning dumps; closer to Llama directness.
GROQ_TEMPERATURE_PRIMARY = float(os.getenv("GROQ_TEMPERATURE_PRIMARY", "0.25") or 0.25)
GROQ_TEMPERATURE_FAST = float(os.getenv("GROQ_TEMPERATURE_FAST", "0.1") or 0.1)
# When true, Company Knowledge uses ops/prompts/pharma-hub/rag-system-bullets.txt
# (gpt-oss / Llama-style). Set false after seeding the same text to Langfuse production.
RAG_PROMPT_USE_LOCAL = os.getenv("RAG_PROMPT_USE_LOCAL", "true").lower() in (
    "1",
    "true",
    "yes",
)

# Optional USD per 1M tokens — sent to Langfuse as cost_details on Groq generations.
# Premium vs free Groq key does not change Langfuse; set prices here or in Langfuse → Models.
GROQ_PRICE_INPUT_PER_1M = float(os.getenv("GROQ_PRICE_INPUT_PER_1M", "0") or 0)
GROQ_PRICE_OUTPUT_PER_1M = float(os.getenv("GROQ_PRICE_OUTPUT_PER_1M", "0") or 0)

# Langfuse (optional — tracing to self-hosted or cloud Langfuse)
LANGFUSE_PUBLIC_KEY = _strip_env_quotes(os.getenv("LANGFUSE_PUBLIC_KEY", ""))
LANGFUSE_SECRET_KEY = _strip_env_quotes(os.getenv("LANGFUSE_SECRET_KEY", ""))
# Accept LANGFUSE_BASE_URL or LANGFUSE_HOST (e.g. http://localhost:3000)
LANGFUSE_HOST = _strip_env_quotes(
    os.getenv("LANGFUSE_BASE_URL") or os.getenv("LANGFUSE_HOST") or ""
)
ENABLE_LANGFUSE_TRACING = os.getenv("ENABLE_LANGFUSE", "true").lower() in (
    "1",
    "true",
    "yes",
)

# OpenObserve (optional — OTLP traces via OpenTelemetry)
ENABLE_OPENOBSERVE = os.getenv("ENABLE_OPENOBSERVE", "false").lower() in (
    "1",
    "true",
    "yes",
)
OPENOBSERVE_URL = _strip_env_quotes(os.getenv("OPENOBSERVE_URL", "http://localhost:5080"))
OPENOBSERVE_ORG = _strip_env_quotes(os.getenv("OPENOBSERVE_ORG", "default"))
OPENOBSERVE_AUTH_TOKEN = _strip_env_quotes(os.getenv("OPENOBSERVE_AUTH_TOKEN", ""))
OPENOBSERVE_SERVICE_NAME = _strip_env_quotes(
    os.getenv("OPENOBSERVE_SERVICE_NAME", os.getenv("POC_ID", "pharma-hub"))
)
OPENOBSERVE_STREAM = _strip_env_quotes(os.getenv("OPENOBSERVE_STREAM", "default"))
OPENOBSERVE_LOGS_STREAM = _strip_env_quotes(
    os.getenv("OPENOBSERVE_LOGS_STREAM", "pharma-hub-logs")
)
OPENOBSERVE_METRICS_STREAM = _strip_env_quotes(
    os.getenv("OPENOBSERVE_METRICS_STREAM", "pharma-hub-metrics")
)

# HTTPS / SSL (corporate proxies often need SSL_CERT_FILE or SSL_VERIFY=false for dev)
SSL_VERIFY = os.getenv("SSL_VERIFY", "true").lower() not in ("0", "false", "no")
SSL_CERT_FILE = _strip_env_quotes(
    os.getenv("SSL_CERT_FILE") or os.getenv("REQUESTS_CA_BUNDLE") or ""
)


def get_ssl_verify():
    """Return requests/httpx `verify` value: False, True, or path to CA bundle."""
    if not SSL_VERIFY:
        return False
    if SSL_CERT_FILE:
        return SSL_CERT_FILE
    return True


def apply_ssl_settings() -> None:
    """
    Apply process-wide SSL settings.

    Groq/NewsAPI use our clients directly, but HuggingFace (sentence-transformers)
    uses `requests` internally — without this, RAG retrieval fails on corporate networks.
    """
    verify = get_ssl_verify()
    if verify is not False:
        if isinstance(verify, str) and verify:
            os.environ.setdefault("REQUESTS_CA_BUNDLE", verify)
            os.environ.setdefault("SSL_CERT_FILE", verify)
        return

    import ssl

    ssl._create_default_https_context = ssl._create_unverified_context  # noqa: SLF001

    try:
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        pass

    try:
        import requests

        _orig_request = requests.Session.request

        def _request_with_verify(self, method, url, **kwargs):
            kwargs.setdefault("verify", False)
            return _orig_request(self, method, url, **kwargs)

        requests.Session.request = _request_with_verify  # type: ignore[method-assign]
    except Exception:
        pass

    try:
        import httpx

        _orig_init = httpx.Client.__init__

        def _client_init(self, *args, **kwargs):
            kwargs.setdefault("verify", False)
            return _orig_init(self, *args, **kwargs)

        httpx.Client.__init__ = _client_init  # type: ignore[method-assign]
    except Exception:
        pass


apply_ssl_settings()

# Neo4j Configuration
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:17687")
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
COMPANY_NEWS_QUICK_ACCESS = _csv_env(
    "COMPANY_NEWS_QUICK_ACCESS",
    ["Pfizer", "Moderna", "Johnson & Johnson", "AstraZeneca", "Dr. Reddy's Laboratories", "Sun Pharma"],
)

# Major pharma news sources
PHARMA_NEWS_SOURCES = [
    "reuters.com",
    "bloomberg.com",
    "fiercepharma.com",
    "biopharmadive.com",
    "endpoints.com"
]

# Drug search: UK/US and common alternate names (improves OpenFDA matching + ranking)
# e.g. OpenFDA labels often use "acetaminophen" while users type "paracetamol"
DRUG_NAME_SYNONYM_GROUPS = _json_env(
    "DRUG_NAME_SYNONYM_GROUPS_JSON",
    [
        ["paracetamol", "acetaminophen"],
        ["epinephrine", "adrenaline"],
        ["lidocaine", "lignocaine"],
    ],
)

# Pharma news query behavior (config-driven, avoids hardcoded tab filters)
PHARMA_NEWS_DEFAULT_QUERY = os.getenv("PHARMA_NEWS_DEFAULT_QUERY", "pharmaceutical drug")
PHARMA_NEWS_CONTEXT_QUERY = os.getenv(
    "PHARMA_NEWS_CONTEXT_QUERY",
    "pharmaceutical OR pharma OR biotech OR drug OR FDA OR vaccine OR medicine OR healthcare OR oncology OR clinical trial OR therapy OR treatment OR patient",
)

# Global guardrail: sidebar toggle defaults here; post-filters news and enriches PubMed / CT.gov queries
ENABLE_PHARMA_GUARDRAIL = os.getenv("ENABLE_PHARMA_GUARDRAIL", "true").lower() in ("1", "true", "yes")
PHARMA_RELEVANCE_KEYWORDS = _csv_env(
    "PHARMA_RELEVANCE_KEYWORDS",
    [
        "pharmaceutical", "pharma", "biotech", "drug", "fda", "vaccine", "medicine",
        "healthcare", "oncology", "clinical trial", "therapy", "treatment", "patient",
        "clinical", "therapeutic", "prescription", "lifesciences", "life sciences",
        "regulatory", "ema", "biologic", "antibody", "pharmacology", "medication",
        "hospital", "physician", "diagnosis", "genomic", "molecule", "placebo",
    ],
)
PUBMED_GUARDRAIL_APPEND = os.getenv(
    "PUBMED_GUARDRAIL_APPEND",
    "(pharmaceutical OR pharma OR biotech OR drug OR medicine OR clinical OR patient OR therapy OR treatment OR vaccine OR FDA OR healthcare OR oncology OR pharmacology OR medical)",
)
CLINICAL_TRIALS_GUARDRAIL_APPEND = os.getenv(
    "CLINICAL_TRIALS_GUARDRAIL_APPEND",
    "(drug OR pharmaceutical OR pharma OR biotech OR vaccine OR therapy OR medicine OR clinical OR device OR patient OR treatment)",
)
# When pharma guardrail is on: refuse free-text search unless the query matches this lexicon
# (avoids generic terms like "engineer" still matching via NewsAPI boolean tricks).
REQUIRE_PHARMA_INTENT_IN_USER_QUERY = os.getenv(
    "REQUIRE_PHARMA_INTENT_IN_USER_QUERY", "true"
).lower() in ("1", "true", "yes")
PHARMA_USER_QUERY_LEXICON = _csv_env(
    "PHARMA_USER_QUERY_LEXICON",
    [
        "cancer", "tumor", "diabetes", "alzheimer", "parkinson", "covid", "hiv",
        "cardiovascular", "immunology", "dermatology", "neurology", "pediatric",
        "metformin", "insulin", "biosimilar", "generics", "antibody", "mrna",
        "gene therapy", "cell therapy", "rare disease", "opioid", "vaccination",
        "randomized", "enrollment", "sponsor", "endpoint", "biomarker", "efficacy",
        "safety", "adverse", "pharmacokinetic", "pharmacodynamic", "informed consent",
    ],
)

# Hybrid retrieval fallback seed keywords (configurable)
RAG_HYBRID_FALLBACK_KEYWORDS = _csv_env(
    "RAG_HYBRID_FALLBACK_KEYWORDS",
    [
        "primary endpoint", "CDR-SB", "ADAS-Cog", "ARIA-E", "ARIA-H",
        "mechanism", "amyloid", "antibody", "efficacy", "safety",
        "adverse", "dose", "administration", "dosing", "protocol",
        "baseline", "Week 72", "results", "outcome",
    ],
)

# Chatbot domain policy text (configurable)
CHATBOT_ENFORCE_DOMAIN_ONLY = os.getenv("CHATBOT_ENFORCE_DOMAIN_ONLY", "true").lower() in ("1", "true", "yes")
CHATBOT_DOMAIN_REFUSAL_TEXT = os.getenv(
    "CHATBOT_DOMAIN_REFUSAL_TEXT",
    "Please ask pharmaceutical-domain questions (drugs, trials, biotech, regulatory, healthcare research).",
)

# Events filtering and query behavior (configurable)
EVENT_MIN_SCORE = int(os.getenv("EVENT_MIN_SCORE", "15"))
EVENT_STRONG_KEYWORDS = _json_env(
    "EVENT_STRONG_KEYWORDS_JSON",
    {
        "hackathon": [
            "hackathon", "hack-a-thon", "coding competition", "coding challenge",
            "innovation challenge", "dev challenge", "datathon",
        ],
        "conference": [
            "conference", "summit", "symposium", "congress", "expo", "forum",
            "annual meeting", "world congress", "international conference",
        ],
        "workshop": [
            "workshop", "webinar", "training session", "masterclass", "bootcamp",
            "short course", "hands-on training", "certification course",
        ],
    },
)
EVENT_ACTION_KEYWORDS = _csv_env(
    "EVENT_ACTION_KEYWORDS",
    [
        "register", "registration", "deadline", "apply", "submit", "join us",
        "attend", "participate", "enroll", "spots available", "virtual event",
        "in-person event", "hybrid event",
    ],
)
EVENT_DATE_KEYWORDS = _csv_env(
    "EVENT_DATE_KEYWORDS",
    [
        "scheduled for", "taking place", "to be held", "dates announced",
        "event date", "happening on", "2026", "2027",
    ],
)
EVENT_EXCLUSION_KEYWORDS = _csv_env(
    "EVENT_EXCLUSION_KEYWORDS",
    [
        "market report", "market analysis", "stock", "shares", "earnings",
        "quarterly report", "revenue", "profit", "financial results",
        "crime", "police", "lawsuit", "litigation", "cagr", "forecast",
        "market size", "merger", "acquisition", "dividend", "price target",
    ],
)
EVENT_PHARMA_KEYWORDS = _csv_env(
    "EVENT_PHARMA_KEYWORDS",
    [
        "pharmaceutical", "pharma", "biotech", "drug", "clinical", "fda",
        "regulatory", "medicine", "therapy", "healthcare", "life sciences",
    ],
)
EVENT_QUERY_HACKATHON = os.getenv(
    "EVENT_QUERY_HACKATHON",
    '(hackathon OR "coding competition" OR "innovation challenge" OR datathon) AND ("pharmaceutical" OR "biotech" OR "healthcare" OR "drug discovery")',
)
EVENT_QUERY_CONFERENCE = os.getenv(
    "EVENT_QUERY_CONFERENCE",
    '(conference OR summit OR congress OR symposium) AND ("pharmaceutical" OR "biotech" OR "clinical trials") AND (2026 OR 2027)',
)
EVENT_QUERY_WORKSHOP = os.getenv(
    "EVENT_QUERY_WORKSHOP",
    '(workshop OR webinar OR training OR "certification course") AND (FDA OR "regulatory affairs" OR "clinical trials" OR GMP)',
)
