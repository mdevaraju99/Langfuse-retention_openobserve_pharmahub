"""list-pocs — show all registered POC configs."""
from __future__ import annotations

from ops.config_loader import POCS_DIR, list_poc_ids, load_poc_config


def run() -> int:
    ids = list_poc_ids()
    if not ids:
        print(f"No POC configs in {POCS_DIR}")
        return 1
    print("Registered POCs:")
    for poc_id in ids:
        try:
            cfg = load_poc_config(poc_id)
            print(f"  - {poc_id}: {cfg.display_name}  prompt={cfg.langfuse.prompt_rag}")
        except Exception as e:
            print(f"  - {poc_id}: (error loading: {e})")
    return 0
