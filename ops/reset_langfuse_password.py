"""
Reset Langfuse UI login password in Postgres (keeps same user + all traces).

Usage (from project root):
  set LANGFUSE_NEW_PASSWORD=YourNewPassword
  python ops/reset_langfuse_password.py --email mdevaraju@aziro.com

Optional:
  set LANGFUSE_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/postgres
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _hash_password(password: str) -> str:
    try:
        import bcrypt
    except ImportError:
        raise SystemExit("Install bcrypt: pip install bcrypt") from None
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters (Langfuse rule).")
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset Langfuse user password in Postgres")
    parser.add_argument("--email", required=True, help="User email (case-insensitive)")
    parser.add_argument(
        "--database-url",
        default=os.getenv(
            "LANGFUSE_DATABASE_URL",
            "postgresql://postgres:postgres@127.0.0.1:5432/postgres",
        ),
    )
    parser.add_argument(
        "--set-email",
        default="",
        help="Optionally change login email (keeps same user id + traces)",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("LANGFUSE_NEW_PASSWORD", ""),
        help="New password (or set LANGFUSE_NEW_PASSWORD env var)",
    )
    args = parser.parse_args()

    email = args.email.strip().lower()
    new_email = (args.set_email or "").strip().lower()
    password = (args.password or os.getenv("LANGFUSE_NEW_PASSWORD", "")).strip()
    if not password:
        print("Set --password or LANGFUSE_NEW_PASSWORD env var.", file=sys.stderr)
        return 1

    try:
        import psycopg2
    except ImportError:
        raise SystemExit("Install psycopg2: pip install psycopg2-binary") from None

    hashed = _hash_password(password)
    if len(hashed) != 60:
        print(f"Unexpected hash length {len(hashed)} (expected 60). Aborting.", file=sys.stderr)
        return 1

    conn = psycopg2.connect(args.database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, length(password) FROM users WHERE lower(email) = %s",
                (email,),
            )
            row = cur.fetchone()
            if not row:
                print(f"No user found with email: {email}", file=sys.stderr)
                print("If Langfuse UI works but user is missing, DATABASE_URL may point to wrong Postgres.", file=sys.stderr)
                return 1

            user_id, db_email, old_len = row
            print(f"Found user id={user_id} email={db_email} old_password_len={old_len}")

            cur.execute(
                """
                UPDATE users
                SET password = %s, email = COALESCE(NULLIF(%s, ''), email), updated_at = NOW()
                WHERE id = %s
                """,
                (hashed, new_email, user_id),
            )
            cur.execute(
                "SELECT email, length(password), updated_at FROM users WHERE id = %s",
                (user_id,),
            )
            verify = cur.fetchone()
        conn.commit()
    finally:
        conn.close()

    print(f"Password updated for {verify[0]} (hash length={verify[1]}, updated_at={verify[2]})")
    print("Sign in at http://localhost:3000/auth/sign-in with the new password.")
    print("Traces are unchanged (same user id). Regenerate API keys if you still get 401.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
