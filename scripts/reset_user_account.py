"""Safe helper for resetting a user account when transactional email isn't available.

Usage patterns (examples):
  # dry-run to show what would happen
  python scripts/reset_user_account.py --db-url "$DB_URL" --old-email alice@example.com --dry-run

  # free the email so you can sign up again (destructive change; requires --yes)
  python scripts/reset_user_account.py --db-url "$DB_URL" --old-email alice@example.com --free-email --yes

  # reassign memberships to an existing new user id, then delete the old user
  python scripts/reset_user_account.py --db-url "$DB_URL" --old-email alice@example.com --reassign-to-user-id 123 --delete-old --yes

Notes:
  - This script assumes a PostgreSQL DB and tables named `users` and `organization_memberships`.
  - It does not attempt to create a usable new user row with a hashed password because hashing
    depends on your auth implementation. The simplest supported flow is to free the old email
    (append a suffix) and then sign up again through your UI.
  - Always backup your database before running destructive operations.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Optional

try:
    import psycopg2
    import psycopg2.extras
except Exception:  # pragma: no cover - helpful message for missing dep
    print("Missing dependency: install psycopg2-binary (pip install psycopg2-binary)")
    raise

try:
    # passlib provides multiple hashers (bcrypt/argon2/pbkdf2)
    from passlib.hash import bcrypt as _bcrypt_hasher
    from passlib.hash import argon2 as _argon2_hasher
    from passlib.hash import pbkdf2_sha256 as _pbkdf2_hasher
except Exception:
    _bcrypt_hasher = None
    _argon2_hasher = None
    _pbkdf2_hasher = None


def get_user(conn, old_email: str) -> Optional[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT * FROM users WHERE email = %s", (old_email,))
        row = cur.fetchone()
        return dict(row) if row else None


def free_email(conn, user_id: int, old_email: str, dry_run: bool = True) -> str:
    suffix = f".deleted.{int(time.time())}"
    new_email = old_email + suffix
    if dry_run:
        print(f"DRY RUN: would update users.id={user_id} email -> {new_email}")
        return new_email

    with conn.cursor() as cur:
        cur.execute("UPDATE users SET email = %s WHERE id = %s RETURNING id", (new_email, user_id))
        if cur.rowcount != 1:
            raise RuntimeError("Expected to update exactly one user row")
    print(f"Updated users.id={user_id} email -> {new_email}")
    return new_email


def reassign_memberships(conn, old_user_id: int, new_user_id: int, dry_run: bool = True) -> int:
    with conn.cursor() as cur:
        if dry_run:
            cur.execute(
                "SELECT count(*) FROM organization_memberships WHERE user_id = %s",
                (old_user_id,),
            )
            n = cur.fetchone()[0]
            print(f"DRY RUN: would update {n} organization_memberships rows user_id {old_user_id} -> {new_user_id}")
            return n

        cur.execute(
            "UPDATE organization_memberships SET user_id = %s WHERE user_id = %s RETURNING id",
            (new_user_id, old_user_id),
        )
        rows = cur.fetchall()
        print(f"Reassigned {len(rows)} organization_memberships rows from user {old_user_id} to {new_user_id}")
        return len(rows)


def delete_user(conn, user_id: int, dry_run: bool = True) -> None:
    if dry_run:
        print(f"DRY RUN: would delete users.id={user_id} (careful: may cascade or fail due to FKs)")
        return

    with conn.cursor() as cur:
        cur.execute("DELETE FROM users WHERE id = %s RETURNING id", (user_id,))
        if cur.rowcount != 1:
            raise RuntimeError("Expected to delete exactly one user row")
    print(f"Deleted users.id={user_id}")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db-url", help="Postgres DSN/URL (or set DATABASE_URL env)")
    p.add_argument("--old-email", required=True, help="Email address of the existing account to free")
    p.add_argument("--free-email", action="store_true", help="Append a suffix to old email to free it for re-signup")
    p.add_argument("--set-password", help="Set a new password for the old user (plain text).")
    p.add_argument(
        "--hash-method",
        choices=("bcrypt", "argon2", "pbkdf2", "plain"),
        default="bcrypt",
        help="Hashing method to use for --set-password (default: bcrypt)",
    )
    p.add_argument("--reassign-to-user-id", type=int, help="Reassign organization_memberships to this user id")
    p.add_argument("--delete-old", action="store_true", help="Delete the old user after reassigning memberships")
    p.add_argument("--dry-run", action="store_true", help="Show SQL actions without committing")
    p.add_argument("--yes", action="store_true", help="Confirm destructive changes")

    args = p.parse_args(argv)
    db_url = args.db_url or os.getenv("DATABASE_URL")
    if not db_url:
        print("Provide --db-url or set DATABASE_URL environment variable")
        return 2

    conn = psycopg2.connect(db_url)
    try:
        conn.autocommit = False
        user = get_user(conn, args.old_email)
        if not user:
            print(f"No user found with email {args.old_email}")
            return 1

        user_id = user["id"]
        print(f"Found user id={user_id} email={user['email']}")

        # handle set-password: detect password-like column and update it
        if args.set_password:
            if not args.dry_run and not args.yes:
                print("Destructive action: pass --yes to confirm")
                return 3

            # detect likely password column
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='users'",
                )
                cols = [r[0] for r in cur.fetchall()]

            candidates = [
                "password",
                "password_hash",
                "password_digest",
                "pw_hash",
                "hashed_password",
                "encrypted_password",
            ]
            target_col = next((c for c in candidates if c in cols), None)
            if not target_col:
                print("Could not detect a password column in users table. Columns found:", cols)
                print("You can specify a column manually by editing the script or updating your schema.")
                return 4

            new_pw_plain = args.set_password
            method = args.hash_method
            if method == "plain":
                hashed = new_pw_plain
            else:
                # choose hasher
                if method == "bcrypt":
                    hasher = _bcrypt_hasher
                elif method == "argon2":
                    hasher = _argon2_hasher
                elif method == "pbkdf2":
                    hasher = _pbkdf2_hasher
                else:
                    hasher = None

                if hasher is None:
                    print(
                        "Hashing library not available. Install passlib with appropriate extras:",
                    )
                    print("pip install 'passlib[argon2]' or 'passlib'")
                    return 5

                hashed = hasher.hash(new_pw_plain)

            if args.dry_run:
                print(f"DRY RUN: would update users.id={user_id} set {target_col} -> <{method} hash>")
            else:
                with conn.cursor() as cur:
                    # IMPORTANT: use parameterized column name via SQL composition
                    cur.execute(
                        f"UPDATE users SET {target_col} = %s WHERE id = %s RETURNING id",
                        (hashed, user_id),
                    )
                    if cur.rowcount != 1:
                        raise RuntimeError("Expected to update exactly one users row when setting password")
                print(f"Updated users.id={user_id} {target_col} with {method} hash")

        if args.free_email:
            if not args.dry_run and not args.yes:
                print("Destructive action: pass --yes to confirm")
                return 3
            new_email = free_email(conn, user_id, args.old_email, dry_run=args.dry_run)
        else:
            new_email = None

        if args.reassign_to_user_id:
            if not args.dry_run and not args.yes:
                print("Destructive action: pass --yes to confirm")
                return 3
            reassign_memberships(conn, user_id, args.reassign_to_user_id, dry_run=args.dry_run)

        if args.delete_old:
            if not args.dry_run and not args.yes:
                print("Destructive action: pass --yes to confirm")
                return 3
            delete_user(conn, user_id, dry_run=args.dry_run)

        if args.dry_run:
            conn.rollback()
            print("DRY RUN: rolled back, no changes made")
        else:
            conn.commit()
            print("Committed changes")
            if new_email:
                print(f"Old email freed: {new_email}")

        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
