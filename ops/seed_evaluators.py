"""seed-evaluators — seed Langfuse managed evaluators into Postgres."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

OPS_ROOT = Path(__file__).resolve().parent
DEFAULT_MANAGED_JSON = Path(
    os.getenv(
        "LANGFUSE_MANAGED_EVALUATORS_JSON",
        r"C:\Users\mdevaraju\langfuse\worker\src\constants\managed-evaluators.json",
    )
)


def _vars_from_prompt(prompt: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\{\{(\w+)\}\}", prompt)))


def _sql_escape(s: str) -> str:
    return s.replace("'", "''")


def _build_sql(evaluators: list[dict]) -> str:
    lines = ["BEGIN;"]
    for ev in evaluators:
        ev_id = _sql_escape(ev["id"])
        name = _sql_escape(ev["name"])
        version = int(ev["version"])
        prompt = _sql_escape(ev["prompt"])
        created = ev["created_at"]
        updated = ev["updated_at"]
        partner = ev.get("partner")
        partner_sql = "NULL" if partner is None else f"'{_sql_escape(str(partner))}'"
        out_json = _sql_escape(json.dumps(ev["outputDefinition"]))
        vars_list = _vars_from_prompt(ev["prompt"])
        vars_pg = "ARRAY[" + ",".join(f"'{_sql_escape(v)}'" for v in vars_list) + "]::text[]"
        lines.append(
            f"""
INSERT INTO eval_templates (
  id, created_at, updated_at, project_id, name, version, prompt,
  partner, output_schema, vars
) VALUES (
  '{ev_id}', '{created}'::timestamptz, '{updated}'::timestamptz, NULL,
  '{name}', {version}, '{prompt}',
  {partner_sql}, '{out_json}'::jsonb, {vars_pg}
)
ON CONFLICT (id) DO UPDATE SET
  updated_at = EXCLUDED.updated_at,
  name = EXCLUDED.name,
  version = EXCLUDED.version,
  prompt = EXCLUDED.prompt,
  partner = EXCLUDED.partner,
  output_schema = EXCLUDED.output_schema,
  vars = EXCLUDED.vars;
""".strip()
        )
    lines.append("COMMIT;")
    return "\n".join(lines)


def run(
    *,
    managed_json: Path | None = None,
    database_url: str | None = None,
    podman_machine: str | None = None,
) -> int:
    json_path = managed_json or DEFAULT_MANAGED_JSON
    if not json_path.is_file():
        print(f"Missing managed evaluators file: {json_path}", file=sys.stderr)
        print("Set LANGFUSE_MANAGED_EVALUATORS_JSON in .env", file=sys.stderr)
        return 1

    db_url = database_url or os.getenv(
        "LANGFUSE_DATABASE_URL",
        "postgresql://postgres:postgres@127.0.0.1:5432/postgres",
    )
    machine = podman_machine or os.getenv("LANGFUSE_PODMAN_MACHINE", "neo4j-machine")

    evaluators = json.loads(json_path.read_text(encoding="utf-8"))
    sql = _build_sql(evaluators)
    sql_file = OPS_ROOT / "seed_langfuse_evaluators.sql"
    sql_file.write_text(sql, encoding="utf-8")

    print(f"Seeding {len(evaluators)} managed evaluators into Langfuse Postgres...")
    result = subprocess.run(
        [
            "podman",
            "machine",
            "ssh",
            machine,
            f"podman run --rm --network host -i docker.io/library/postgres:17 "
            f"psql {db_url} -v ON_ERROR_STOP=1",
        ],
        input=sql,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        print(result.stderr or "psql failed", file=sys.stderr)
        return result.returncode

    names = ", ".join(sorted({e["name"] for e in evaluators}))
    print(f"Done. Templates available: {names}")
    print("SQL saved to:", sql_file)
    return 0
