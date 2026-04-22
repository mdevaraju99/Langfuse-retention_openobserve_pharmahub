"""
Answer validation utilities for grounded RAG responses.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Dict, List


@dataclass
class ValidationResult:
    confidence: int
    has_citations: bool
    citation_count: int
    grounded_ratio: float
    issues: List[str]
    decision: str  # pass | warn | fail

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["grounded_ratio"] = round(float(self.grounded_ratio), 3)
        return d


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9\-\%]{2,}", (text or "").lower())


def _split_sentences(text: str) -> List[str]:
    if not text:
        return []
    parts = re.split(r"(?<=[\.\!\?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def validate_answer(answer: str, context: str, min_grounded_ratio: float = 0.35) -> ValidationResult:
    """
    Heuristic validation:
    - citation presence
    - sentence-level grounding overlap with context vocabulary
    - basic issue detection for low grounding
    """
    ans = answer or ""
    ctx = context or ""
    issues: List[str] = []

    citations = re.findall(r"\[[^\]]+\.pdf\]", ans, flags=re.IGNORECASE)
    has_citations = len(citations) > 0
    if not has_citations:
        issues.append("No source citations found.")

    ctx_vocab = set(_tokenize(ctx))
    sents = _split_sentences(ans)
    if not sents:
        return ValidationResult(
            confidence=10,
            has_citations=has_citations,
            citation_count=len(citations),
            grounded_ratio=0.0,
            issues=["Empty answer."],
            decision="fail",
        )

    grounded_hits = 0
    for sent in sents:
        tokens = _tokenize(sent)
        if not tokens:
            continue
        overlap = sum(1 for t in tokens if t in ctx_vocab)
        ratio = overlap / max(1, len(tokens))
        if ratio >= min_grounded_ratio:
            grounded_hits += 1

    grounded_ratio = grounded_hits / max(1, len(sents))
    if grounded_ratio < 0.25:
        issues.append("Low grounding against retrieved context.")
    elif grounded_ratio < 0.5:
        issues.append("Partial grounding; verify key claims.")

    # Confidence scoring (0-100)
    score = 35
    score += min(25, len(citations) * 6)
    score += int(grounded_ratio * 40)
    if "Low grounding against retrieved context." in issues:
        score -= 20
    score = max(0, min(100, score))

    if score >= 75:
        decision = "pass"
    elif score >= 45:
        decision = "warn"
    else:
        decision = "fail"

    return ValidationResult(
        confidence=score,
        has_citations=has_citations,
        citation_count=len(citations),
        grounded_ratio=grounded_ratio,
        issues=issues,
        decision=decision,
    )
