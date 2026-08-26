"""seed-all — health check + seed production prompt for a POC."""
from __future__ import annotations

from ops import health, seed_prompt
from ops.config_loader import PocConfig


def run(cfg: PocConfig) -> int:
    print("=== Step 1/2: health ===")
    if health.run(cfg, send_trace=False) != 0:
        return 1
    print()
    print("=== Step 2/2: seed-prompt (production) ===")
    return seed_prompt.run(cfg, variant="production")
