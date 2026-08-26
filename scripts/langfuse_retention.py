"""Apply age- and size-based retention to Langfuse traces.

This is intended for self-hosted Langfuse OSS, where the built-in retention
policy is not available. It uses only Langfuse's public API, so it can also be
pointed at another self-hosted instance or Langfuse Cloud.

The two policy parameters are:

1. --retention-days: delete traces older than this many days.
2. --max-size-mb: after age cleanup, delete the oldest remaining traces until
   their estimated API payload is below this upper limit.

The size is a logical trace-payload estimate (compact UTF-8 JSON returned by
the API), not exact ClickHouse/MinIO/Podman disk usage. Database compression,
indexes, system logs, images, and unused container images are outside this
limit.

Safety: the script is a dry run unless --apply is supplied.

Examples:
    python scripts/langfuse_retention.py
    python scripts/langfuse_retention.py --retention-days 30 --max-size-mb 1024
    python scripts/langfuse_retention.py --retention-days 30 --max-size-mb 1024 --apply
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_RETENTION_DAYS = 30
DEFAULT_MAX_SIZE_MB = 1024.0  # 1 GiB logical trace payload
DELETE_BATCH_SIZE = 1000  # Langfuse API maximum
LIST_PAGE_SIZE = 100


@dataclass(frozen=True)
class TraceSummary:
    trace_id: str
    timestamp: datetime
    estimated_bytes: int


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Delete Langfuse traces by age and retained logical payload size. "
            "Dry-run is the default."
        )
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=DEFAULT_RETENTION_DAYS,
        help=f"Delete traces older than this many days (default: {DEFAULT_RETENTION_DAYS})",
    )
    parser.add_argument(
        "--max-size-mb",
        type=float,
        default=DEFAULT_MAX_SIZE_MB,
        help=(
            "Maximum estimated retained trace payload in MiB; oldest traces are "
            f"removed first (default: {DEFAULT_MAX_SIZE_MB:g})"
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform deletion. Without this flag, only print the retention plan.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help=f"Environment file (default: {DEFAULT_ENV_FILE})",
    )
    args = parser.parse_args()
    if args.retention_days < 1:
        parser.error("--retention-days must be at least 1")
    if args.max_size_mb <= 0:
        parser.error("--max-size-mb must be greater than 0")
    return args


def _required_env(name: str) -> str:
    value = (os.getenv(name) or "").strip().strip("\"'")
    if not value:
        raise RuntimeError(f"Missing {name} in environment/.env")
    return value


def _verify_setting() -> bool | str:
    if (os.getenv("SSL_VERIFY") or "true").lower() in {"0", "false", "no"}:
        return False
    ca_file = (
        (os.getenv("SSL_CERT_FILE") or "").strip().strip("\"'")
        or (os.getenv("REQUESTS_CA_BUNDLE") or "").strip().strip("\"'")
    )
    return ca_file or True


def _session(public_key: str, secret_key: str) -> requests.Session:
    token = base64.b64encode(f"{public_key}:{secret_key}".encode("utf-8")).decode("ascii")
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    )
    return session


def _parse_timestamp(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("trace has no timestamp")
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _estimate_bytes(trace: dict[str, Any]) -> int:
    compact = json.dumps(
        trace,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return len(compact.encode("utf-8"))


def _list_traces(
    session: requests.Session,
    base_url: str,
    verify: bool | str,
) -> list[TraceSummary]:
    endpoint = f"{base_url}/api/public/traces"
    page = 1
    traces: list[TraceSummary] = []

    while True:
        response = session.get(
            endpoint,
            params={
                "page": page,
                "limit": LIST_PAGE_SIZE,
                "fromTimestamp": "1970-01-01T00:00:00Z",
                "orderBy": "timestamp.asc",
                "fields": "core,io,scores,observations,metrics",
            },
            timeout=60,
            verify=verify,
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("data") or []

        for row in rows:
            trace_id = str(row.get("id") or "").strip()
            if not trace_id:
                continue
            try:
                timestamp = _parse_timestamp(row.get("timestamp"))
            except ValueError as exc:
                print(f"Warning: skipping trace {trace_id}: {exc}", file=sys.stderr)
                continue
            traces.append(
                TraceSummary(
                    trace_id=trace_id,
                    timestamp=timestamp,
                    estimated_bytes=_estimate_bytes(row),
                )
            )

        meta = payload.get("meta") or {}
        total_pages = int(meta.get("totalPages") or page)
        print(
            f"\rScanned page {page}/{total_pages} ({len(traces)} traces)",
            end="",
            flush=True,
        )
        if not rows or page >= total_pages:
            break
        page += 1

    print()
    traces.sort(key=lambda trace: trace.timestamp)
    return traces


def _build_plan(
    traces: list[TraceSummary],
    cutoff: datetime,
    max_bytes: int,
) -> tuple[list[TraceSummary], list[TraceSummary], list[TraceSummary]]:
    age_deletions = [trace for trace in traces if trace.timestamp < cutoff]
    age_ids = {trace.trace_id for trace in age_deletions}
    retained = [trace for trace in traces if trace.trace_id not in age_ids]

    retained_bytes = sum(trace.estimated_bytes for trace in retained)
    size_deletions: list[TraceSummary] = []
    for trace in retained:
        if retained_bytes <= max_bytes:
            break
        size_deletions.append(trace)
        retained_bytes -= trace.estimated_bytes

    size_ids = {trace.trace_id for trace in size_deletions}
    final_retained = [trace for trace in retained if trace.trace_id not in size_ids]
    return age_deletions, size_deletions, final_retained


def _mib(value: int) -> float:
    return value / (1024 * 1024)


def _delete_traces(
    session: requests.Session,
    base_url: str,
    verify: bool | str,
    traces: list[TraceSummary],
) -> None:
    endpoint = f"{base_url}/api/public/traces"
    ids = [trace.trace_id for trace in traces]
    for start in range(0, len(ids), DELETE_BATCH_SIZE):
        batch = ids[start : start + DELETE_BATCH_SIZE]
        response = session.delete(
            endpoint,
            json={"traceIds": batch},
            timeout=120,
            verify=verify,
        )
        response.raise_for_status()
        print(f"Deleted batch: {len(batch)} traces")


def main() -> int:
    args = _parse_args()
    if args.env_file.is_file():
        load_dotenv(args.env_file, override=False)

    try:
        base_url = _required_env("LANGFUSE_BASE_URL").rstrip("/")
        public_key = _required_env("LANGFUSE_PUBLIC_KEY")
        secret_key = _required_env("LANGFUSE_SECRET_KEY")
    except RuntimeError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    verify = _verify_setting()
    session = _session(public_key, secret_key)
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.retention_days)
    max_bytes = int(args.max_size_mb * 1024 * 1024)

    print("Langfuse retention policy")
    print("-" * 64)
    print(f"Host:                 {base_url}")
    print(f"Retention period:     {args.retention_days} days")
    print(f"Age cutoff (UTC):     {cutoff.isoformat(timespec='seconds')}")
    print(f"Trace payload ceiling:{args.max_size_mb:>10,.2f} MiB")
    print(f"Mode:                 {'APPLY (destructive)' if args.apply else 'DRY RUN'}")
    print()

    try:
        traces = _list_traces(session, base_url, verify)
    except requests.RequestException as exc:
        print(f"Langfuse API error while listing traces: {exc}", file=sys.stderr)
        return 1

    age_deletions, size_deletions, final_retained = _build_plan(
        traces,
        cutoff,
        max_bytes,
    )
    deletions_by_id = {
        trace.trace_id: trace for trace in age_deletions + size_deletions
    }
    deletions = sorted(deletions_by_id.values(), key=lambda trace: trace.timestamp)

    current_bytes = sum(trace.estimated_bytes for trace in traces)
    delete_bytes = sum(trace.estimated_bytes for trace in deletions)
    final_bytes = sum(trace.estimated_bytes for trace in final_retained)

    print("\nRetention plan")
    print("-" * 64)
    print(f"Current traces:        {len(traces):>10,}")
    print(f"Current payload:       {_mib(current_bytes):>10,.2f} MiB (estimated)")
    print(f"Delete by age:         {len(age_deletions):>10,}")
    print(f"Delete by size:        {len(size_deletions):>10,}")
    print(f"Total unique deletes:  {len(deletions):>10,}")
    print(f"Payload to delete:     {_mib(delete_bytes):>10,.2f} MiB (estimated)")
    print(f"Final retained traces: {len(final_retained):>10,}")
    print(f"Final payload:         {_mib(final_bytes):>10,.2f} MiB (estimated)")

    if not deletions:
        print("\nNo traces need deletion.")
        return 0

    oldest = deletions[0].timestamp.isoformat(timespec="seconds")
    newest = deletions[-1].timestamp.isoformat(timespec="seconds")
    print(f"Deletion timestamp range: {oldest} through {newest}")

    if not args.apply:
        print("\nDRY RUN ONLY: nothing was deleted.")
        print("Re-run with --apply after reviewing this plan.")
        return 0

    try:
        _delete_traces(session, base_url, verify, deletions)
    except requests.RequestException as exc:
        print(f"Langfuse API error while deleting traces: {exc}", file=sys.stderr)
        return 1

    print(
        "\nDeletion requests accepted. Langfuse processes trace cleanup "
        "asynchronously, so disk space may not drop immediately."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
