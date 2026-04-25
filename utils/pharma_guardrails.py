"""
Shared pharma relevance guardrails for search/news tabs.
Uses sidebar session state (initialized in app.py) with config defaults.
"""
from __future__ import annotations

import re
from typing import Any

import streamlit as st

import config


def guardrail_enabled() -> bool:
    try:
        return bool(
            st.session_state.get(
                "pharma_guardrail_enabled",
                getattr(config, "ENABLE_PHARMA_GUARDRAIL", True),
            )
        )
    except Exception:
        return bool(getattr(config, "ENABLE_PHARMA_GUARDRAIL", True))


def relevance_keywords() -> list[str]:
    kws = list(getattr(config, "PHARMA_RELEVANCE_KEYWORDS", []) or [])
    return [k.strip().lower() for k in kws if k and str(k).strip()]


def _lexicon_add(seen: set[str], out: list[str], token: str) -> None:
    k = (token or "").strip().lower()
    if len(k) < 2 or k in seen:
        return
    seen.add(k)
    out.append(k)


def user_query_lexicon() -> list[str]:
    """Tokens/phrases that indicate the user is searching in-domain (companies, drugs, clinical, etc.)."""
    seen: set[str] = set()
    out: list[str] = []
    for k in relevance_keywords():
        _lexicon_add(seen, out, k)
    for k in getattr(config, "PHARMA_USER_QUERY_LEXICON", []) or []:
        _lexicon_add(seen, out, str(k))
    for company in getattr(config, "PHARMA_COMPANIES", []) or []:
        _lexicon_add(seen, out, _normalize_blob(company))
        for w in re.findall(r"[a-z0-9]+", company.lower()):
            if len(w) >= 4:
                _lexicon_add(seen, out, w)
    for group in getattr(config, "DRUG_NAME_SYNONYM_GROUPS", []) or []:
        for w in group or []:
            _lexicon_add(seen, out, str(w))
    return out


def require_pharma_intent_in_user_query() -> bool:
    return guardrail_enabled() and bool(
        getattr(config, "REQUIRE_PHARMA_INTENT_IN_USER_QUERY", True)
    )


def user_search_allowed(raw_input: str, normalized: str) -> bool:
    """
    If guardrail + REQUIRE_PHARMA_INTENT: non-empty search must hit the user-query lexicon.
    Empty search is allowed (tabs use their default pharma query).
    """
    if not require_pharma_intent_in_user_query():
        return True
    combined = f"{raw_input or ''} {normalized or ''}".strip()
    if not combined:
        return True
    compact = re.sub(r"\s+", "", combined.lower())
    if re.search(r"nct\d{6,}", compact):
        return True
    kws = user_query_lexicon()
    if not kws:
        return True
    return keyword_hit_count(_normalize_blob(combined), kws) >= 1


def _normalize_blob(text: str) -> str:
    return " ".join((text or "").lower().split())


def keyword_hit_count(text: str, keywords: list[str] | None = None) -> int:
    """Count how many distinct configured keywords appear in text (word-safe for single tokens)."""
    kws = keywords if keywords is not None else relevance_keywords()
    blob = _normalize_blob(text)
    if not blob or not kws:
        return 0
    hits = 0
    for kw in kws:
        k = (kw or "").strip().lower()
        if not k:
            continue
        if " " in k:
            if k in blob:
                hits += 1
        elif re.search(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])", blob):
            hits += 1
    return hits


def news_article_blob(article: dict[str, Any]) -> str:
    title = article.get("title") or ""
    desc = article.get("description") or ""
    return f"{title} {desc}"


def filter_pharma_relevant_news(
    articles: list[dict[str, Any]],
    min_hits: int = 1,
) -> list[dict[str, Any]]:
    if not articles or not guardrail_enabled():
        return articles
    kws = relevance_keywords()
    if not kws:
        return articles
    out: list[dict[str, Any]] = []
    for a in articles:
        if keyword_hit_count(news_article_blob(a), kws) >= min_hits:
            out.append(a)
    return out


def enrich_pubmed_query(user_query: str) -> str:
    core = (user_query or "").strip()
    if not core:
        core = "pharmaceutical drug development"
    if not guardrail_enabled():
        return core
    extra = str(getattr(config, "PUBMED_GUARDRAIL_APPEND", "") or "").strip()
    if not extra:
        return core
    return f"({core}) AND ({extra})"


def enrich_clinical_trials_query(user_query: str) -> str:
    core = (user_query or "").strip()
    if not core:
        core = "cancer"
    if not guardrail_enabled():
        return core
    extra = str(getattr(config, "CLINICAL_TRIALS_GUARDRAIL_APPEND", "") or "").strip()
    if not extra:
        return core
    return f"({core}) AND ({extra})"
