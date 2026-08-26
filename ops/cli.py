#!/usr/bin/env python3
"""
All Langfuse / multi-POC ops live in this folder (ops/).

Usage:
  python ops/cli.py list-pocs
  python ops/cli.py info --poc pharma-hub
  python ops/cli.py health --poc pharma-hub
  python ops/cli.py health-openobserve
  python ops/cli.py openobserve-guide
  python ops/cli.py seed-prompt --poc pharma-hub --variant bullets
  python ops/cli.py seed-all --poc pharma-hub
  python ops/cli.py seed-evaluators
  python ops/cli.py print-scores --poc pharma-hub --trace-id <id>

Environment:
  POC_ID                         default POC when --poc omitted
  LANGFUSE_*                     from project .env
  LANGFUSE_MANAGED_EVALUATORS_JSON   path to managed-evaluators.json
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

OPS_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = OPS_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ops import health, health_openobserve, info, list_pocs, openobserve_guide, print_scores, seed_all, seed_evaluators, seed_prompt  # noqa: E402
from ops.config_loader import load_poc_config  # noqa: E402


def _resolve_poc(args: argparse.Namespace) -> str:
    poc = getattr(args, "poc", None) or os.getenv("POC_ID", "").strip()
    if not poc:
        raise SystemExit("Missing --poc (or set POC_ID in .env)")
    return poc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Langfuse ops — single folder, multiple POCs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=PROJECT_ROOT / ".env",
        help="Path to .env (default: project root .env)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-pocs", help="List registered POC YAML configs")

    p_info = sub.add_parser("info", help="Show POC Langfuse config")
    p_info.add_argument("--poc", help="POC id (e.g. pharma-hub)")

    p_health = sub.add_parser("health", help="Verify Langfuse keys + optional test trace")
    p_health.add_argument("--poc", help="POC id")
    p_health.add_argument("--no-trace", action="store_true", help="Skip test trace")

    p_oo = sub.add_parser("health-openobserve", help="Verify OpenObserve OTLP + optional test trace")
    p_oo.add_argument("--poc", help="POC id (for span attributes)")
    p_oo.add_argument("--no-trace", action="store_true", help="Skip test trace")

    sub.add_parser("openobserve-guide", help="Print how to use every OpenObserve feature with this POC")

    p_seed = sub.add_parser("seed-prompt", help="Push prompt file to Langfuse")
    p_seed.add_argument("--poc", help="POC id")
    p_seed.add_argument(
        "--variant",
        default="production",
        choices=["production", "bullets", "baseline"],
        help="Which prompt file from prompts/<poc>/",
    )
    p_seed.add_argument("--label", default=None, help="Langfuse label (default: from POC yaml)")

    p_all = sub.add_parser("seed-all", help="Health + seed production prompt")
    p_all.add_argument("--poc", help="POC id")

    sub.add_parser("seed-evaluators", help="Seed managed evaluators into Langfuse Postgres")

    p_scores = sub.add_parser("print-scores", help="Print score comments for a trace")
    p_scores.add_argument("--poc", help="POC id")
    p_scores.add_argument("--trace-id", required=True, help="Langfuse trace id")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "list-pocs":
        return list_pocs.run()

    if args.command == "seed-evaluators":
        return seed_evaluators.run()

    if args.command == "health-openobserve":
        poc = getattr(args, "poc", None) or os.getenv("POC_ID", "pharma-hub").strip() or "pharma-hub"
        return health_openobserve.run(poc_id=poc, send_trace=not args.no_trace)

    if args.command == "openobserve-guide":
        return openobserve_guide.run()

    poc_id = _resolve_poc(args)
    cfg = load_poc_config(poc_id, env_file=args.env_file)

    if args.command == "info":
        return info.run(cfg)
    if args.command == "health":
        return health.run(cfg, send_trace=not args.no_trace)
    if args.command == "seed-prompt":
        return seed_prompt.run(cfg, variant=args.variant, label=args.label)
    if args.command == "seed-all":
        return seed_all.run(cfg)
    if args.command == "print-scores":
        return print_scores.run(cfg, args.trace_id)

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
