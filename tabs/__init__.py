from __future__ import annotations

import importlib
from typing import List

__all__: List[str] = [
    "analytics",
    "case_studies",
    "chatbot",
    "clinical_trials",
    "company_knowledge",
    "company_news",
    "drug_info",
    "events",
    "pharma_news",
    "regulatory",
    "research_papers",
]


def __getattr__(name: str):
    if name in __all__:
        return importlib.import_module("." + name, __package__)
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


def __dir__() -> List[str]:
    return sorted(__all__)
