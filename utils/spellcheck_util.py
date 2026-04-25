"""
Lightweight spell suggestions for user queries (offline, pyspellchecker).
"""
from __future__ import annotations

from typing import List, Tuple

# Lazy singleton to avoid import cost on cold start
_spell = None


def _get_spell():
    global _spell
    if _spell is None:
        from spellchecker import SpellChecker

        # distance=2 catches leading-letter typos like "rcancer" -> "cancer"
        _spell = SpellChecker(distance=2)
    return _spell


def suggest_for_text(text: str, max_suggestions: int = 8) -> List[Tuple[str, str]]:
    """
    Return list of (original_token, suggestion) for likely misspellings.
    Skips short tokens, URLs, and all-caps acronyms.
    """
    if not text or not text.strip():
        return []

    spell = _get_spell()
    out: List[Tuple[str, str]] = []
    seen = set()

    for raw in text.replace("\n", " ").split():
        token = raw.strip().strip(".,;:!?()[]'\"")
        if len(token) < 3:
            continue
        if token.isupper():
            continue
        if "http" in token.lower() or "@" in token:
            continue

        w = token.lower()
        if w in spell:
            continue
        cand = spell.correction(w)
        if not cand or cand == w:
            continue
        key = (token, cand)
        if key in seen:
            continue
        seen.add(key)
        out.append((token, cand))
        if len(out) >= max_suggestions:
            break

    return out


def normalize_query_text(text: str) -> tuple[str, list[tuple[str, str]]]:
    """
    Return (normalized_query, list of (original_token, correction)) for tokens we changed.
    Preserves spacing between words; skips URLs, numbers-heavy tokens, and ALL-CAPS acronyms.
    """
    if not text or not text.strip():
        return text.strip(), []

    spell = _get_spell()
    corrections: List[Tuple[str, str]] = []
    out_tokens: List[str] = []

    for raw in text.split():
        if not raw:
            continue

        leading = ""
        trailing = ""
        core = raw
        # keep simple edge punctuation split
        while core and not core[0].isalnum():
            leading += core[0]
            core = core[1:]
        while core and not core[-1].isalnum():
            trailing = core[-1] + trailing
            core = core[:-1]

        if len(core) < 3:
            out_tokens.append(raw)
            continue
        if any(ch.isdigit() for ch in core):
            out_tokens.append(raw)
            continue
        if "http" in core.lower() or "@" in core:
            out_tokens.append(raw)
            continue
        if core.isupper() and len(core) <= 5:
            out_tokens.append(raw)
            continue

        w = core.lower()
        if w in spell:
            out_tokens.append(raw)
            continue

        cand = spell.correction(w) or w
        if cand != w:
            corrections.append((core, cand))
            # keep original casing style loosely: all-lower output for search APIs
            fixed = leading + cand + trailing
            out_tokens.append(fixed)
        else:
            out_tokens.append(raw)

    normalized = " ".join(out_tokens).strip()
    return normalized, corrections


def candidates_for_tokens(text: str, max_per_token: int = 12) -> list[str]:
    """
    Return distinct spelling candidates for each non-dictionary token (for "Did you mean" lists).
    """
    if not text or not text.strip():
        return []

    spell = _get_spell()
    out: list[str] = []
    seen: set[str] = set()

    for raw in text.replace("\n", " ").split():
        token = raw.strip().strip(".,;:!?()[]'\"")
        if len(token) < 3 or token.isupper():
            continue
        w = token.lower()
        if w in spell:
            continue
        try:
            cands = spell.candidates(w)
        except Exception:
            cands = None
        if not cands:
            cand = spell.correction(w)
            cands = {cand} if cand and cand != w else set()
        for c in list(cands)[:max_per_token]:
            if not c or c == w:
                continue
            if c.lower() not in seen:
                seen.add(c.lower())
                out.append(c)
            if len(out) >= max_per_token * 2:
                break
    return out
