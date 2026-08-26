"""seed-prompt — push a prompt file from ops/prompts/<poc>/ to Langfuse."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ops.config_loader import PocConfig
from ops.langfuse_ops import seed_prompt as push_prompt


def _resolve_prompt_file(cfg: PocConfig, variant: str) -> Path:
    files = cfg.prompt_files
    key_map = {
        "production": files.get("production_file") or files.get("bullets_file"),
        "bullets": files.get("bullets_file") or files.get("production_file"),
        "baseline": files.get("baseline_file"),
    }
    filename = key_map.get(variant) or files.get(variant)
    if not filename:
        raise FileNotFoundError(
            f"No prompt file mapped for variant '{variant}' in pocs/{cfg.poc_id}.yaml "
            f"(keys: {list(files.keys())})"
        )
    path = cfg.prompts_dir / filename
    if not path.is_file():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path


def run(
    cfg: PocConfig,
    *,
    variant: str = "production",
    label: Optional[str] = None,
) -> int:
    path = _resolve_prompt_file(cfg, variant)
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        print(f"Prompt file is empty: {path}")
        return 1

    prompt_label = label if label is not None else cfg.langfuse.prompt_label
    print(f"Seeding prompt for POC '{cfg.poc_id}'")
    print(f"  name:     {cfg.langfuse.prompt_rag}")
    print(f"  label:    {prompt_label}")
    print(f"  variant:  {variant}")
    print(f"  file:     {path}")
    print(f"  chars:    {len(text)}")

    version = push_prompt(
        cfg,
        text,
        label=prompt_label,
        config_meta={"poc_id": cfg.poc_id, "variant": variant},
    )
    print(f"Done — created version {version}")
    print("Restart Streamlit (or clear prompt cache) to pick up production label.")
    return 0
