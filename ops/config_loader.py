"""Load per-POC YAML config + Langfuse credentials from environment."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dotenv import load_dotenv

OPS_ROOT = Path(__file__).resolve().parent
POCS_DIR = OPS_ROOT / "pocs"
PROMPTS_DIR = OPS_ROOT / "prompts"


def _strip_quotes(value: str) -> str:
    s = (value or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1].strip()
    return s


def _env(name: str, default: str = "") -> str:
    return _strip_quotes(os.getenv(name, default))


@dataclass
class LangfuseConfig:
    public_key: str
    secret_key: str
    host: str
    prompt_rag: str = "pharma/rag-system"
    prompt_label: str = "production"
    tags: List[str] = field(default_factory=list)
    trace_rag: str = "company_knowledge"
    trace_chat: str = "chatbot"


@dataclass
class PocConfig:
    poc_id: str
    display_name: str
    langfuse: LangfuseConfig
    scores_auto: List[str] = field(default_factory=list)
    human_queue: str = ""
    golden_dataset: str = ""
    prompt_files: Dict[str, str] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def prompts_dir(self) -> Path:
        return PROMPTS_DIR / self.poc_id


def list_poc_ids() -> List[str]:
    if not POCS_DIR.is_dir():
        return []
    return sorted(p.stem for p in POCS_DIR.glob("*.yaml"))


def load_poc_config(
    poc_id: str,
    *,
    env_file: Optional[Path] = None,
) -> PocConfig:
    """Load POC YAML and merge Langfuse keys from .env (or poc-specific env vars)."""
    if env_file and env_file.is_file():
        load_dotenv(env_file, override=False)
    else:
        # Project root .env when run from Pharma_final_version1
        root_env = OPS_ROOT.parent / ".env"
        if root_env.is_file():
            load_dotenv(root_env, override=False)

    yaml_path = POCS_DIR / f"{poc_id}.yaml"
    if not yaml_path.is_file():
        raise FileNotFoundError(f"POC config not found: {yaml_path}")

    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    lf = data.get("langfuse") or {}

    pk_env = lf.get("public_key_env", "LANGFUSE_PUBLIC_KEY")
    sk_env = lf.get("secret_key_env", "LANGFUSE_SECRET_KEY")
    host_env = lf.get("host_env", "LANGFUSE_BASE_URL")

    # Optional per-POC key override: LANGFUSE_PUBLIC_KEY__pharma-hub
    poc_suffix = poc_id.upper().replace("-", "_")
    public_key = _env(f"{pk_env}__{poc_suffix}") or _env(pk_env)
    secret_key = _env(f"{sk_env}__{poc_suffix}") or _env(sk_env)
    host = _env(f"{host_env}__{poc_suffix}") or _env(host_env) or _env("LANGFUSE_HOST")

    trace_names = lf.get("trace_names") or {}
    langfuse_cfg = LangfuseConfig(
        public_key=public_key,
        secret_key=secret_key,
        host=host.rstrip("/"),
        prompt_rag=lf.get("prompt_rag", "pharma/rag-system"),
        prompt_label=lf.get("prompt_label", "production"),
        tags=list(lf.get("tags") or []),
        trace_rag=trace_names.get("rag", "company_knowledge"),
        trace_chat=trace_names.get("chat", "chatbot"),
    )

    scores = data.get("scores") or {}
    datasets = data.get("datasets") or {}
    prompts = data.get("prompts") or {}

    return PocConfig(
        poc_id=data.get("poc_id", poc_id),
        display_name=data.get("display_name", poc_id),
        langfuse=langfuse_cfg,
        scores_auto=list(scores.get("auto") or []),
        human_queue=str(scores.get("human_queue") or ""),
        golden_dataset=str(datasets.get("golden") or ""),
        prompt_files=dict(prompts),
        raw=data,
    )
