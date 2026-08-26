"""info — print POC Langfuse configuration (no API calls)."""
from __future__ import annotations

from ops.config_loader import PocConfig


def run(cfg: PocConfig) -> int:
    lf = cfg.langfuse
    print(f"POC: {cfg.poc_id}")
    print(f"  display_name:   {cfg.display_name}")
    print(f"  prompt:         {lf.prompt_rag} @ {lf.prompt_label}")
    print(f"  trace (rag):    {lf.trace_rag}")
    print(f"  trace (chat):   {lf.trace_chat}")
    print(f"  tags:           {lf.tags}")
    print(f"  auto scores:    {cfg.scores_auto}")
    print(f"  human queue:    {cfg.human_queue or '(none)'}")
    print(f"  golden dataset: {cfg.golden_dataset or '(none)'}")
    print(f"  prompt files:   {cfg.prompt_files}")
    return 0
