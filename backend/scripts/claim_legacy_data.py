# ruff: noqa: E501
"""Attach the pre-authentication ("legacy") data to the owner's real Clerk account, safely.

    export DATABASE_URL='postgresql+psycopg://...'      # the production database
    export CLERK_SECRET_KEY='sk_live_...'               # the instance the owner signs in to
    python scripts/claim_legacy_data.py inspect --clerk-user-id user_XXXX
    python scripts/claim_legacy_data.py claim   --clerk-user-id user_XXXX --expect-email me@example.com \\
        --instance live --backup /path/optima-pars-....sqlite --timezone account            # dry run
    python scripts/claim_legacy_data.py claim ... --execute --confirm-clerk-id user_XXXX      # for real

The only change this ever makes is linking one existing user row to one Clerk id (and removing the
empty account that signing in created). No book, note, task or project row is touched, so every
relationship is preserved. It refuses to do even that unless ALL of these hold:

  1. Clerk itself confirms the id exists, belongs to the instance you named (live or test), has the
     email address you expect, and that address is verified;
  2. the legacy user is still unlinked, and the new account owns nothing;
  3. a verified backup exists, is under an hour old, and the database has not changed since;
  4. you typed the Clerk id twice and, if the new account has settings, chose whose timezone wins.

It defaults to a dry run. Nothing is written without --execute.
"""

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backup_postgres import manifest_path, verify_backup  # noqa: E402
from sqlalchemy import create_engine, delete, select, text, update  # noqa: E402

from app.core.config import LEGACY_USER_ID  # noqa: E402
from app.db import Base  # noqa: E402
from app.models import User  # noqa: E402

CLERK_API = "https://api.clerk.com/v1"
MAX_BACKUP_AGE = timedelta(hours=1)


class Refused(Exception):
    """A safety condition failed; nothing was changed."""


def fetch_clerk_user(secret_key: str, clerk_user_id: str) -> dict:
    """The user as Clerk reports it (one authenticated GET; the key is never printed)."""
    response = httpx.get(f"{CLERK_API}/users/{clerk_user_id}", headers={"Authorization": f"Bearer {secret_key}"}, timeout=15)
    if response.status_code == 404:
        raise Refused(f"Clerk has no user {clerk_user_id} in the instance this secret key belongs to.")
    if response.status_code != 200:
        raise Refused(f"Clerk answered {response.status_code}; cannot verify the account.")
    return response.json()


def primary_email(user: dict) -> tuple[str | None, bool]:
    primary = user.get("primary_email_address_id")
    for address in user.get("email_addresses", []):
        if address.get("id") == primary:
            return address.get("email_address"), (address.get("verification") or {}).get("status") == "verified"
    return None, False


def owned_counts(connection, user_id) -> dict[str, int]:
    counts = {}
    for table in Base.metadata.sorted_tables:
        if "user_id" in table.c:
            n = connection.execute(select(text("count(*)")).select_from(table).where(table.c.user_id == user_id)).scalar()
            if n:
                counts[table.name] = n
    return counts


def table_totals(connection) -> dict[str, int]:
    return {t.name: connection.execute(select(text("count(*)")).select_from(t)).scalar() for t in Base.metadata.sorted_tables}


def secret_key() -> str:
    key = os.environ.get("CLERK_SECRET_KEY", "")
    if not key:
        raise Refused("Set CLERK_SECRET_KEY (the instance the owner signs in to) in the environment.")
    return key


def engine_for_env():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise Refused("Set DATABASE_URL in the environment.")
    return create_engine(url)


def describe_database(engine) -> str:
    url = engine.url  # host and name only: never the password
    return f"{url.get_backend_name()}://{url.host or ''}/{url.database or ''}"


def rows_summary(counts: dict[str, int]) -> str:
    return ", ".join(f"{name} {n}" for name, n in counts.items()) or "nothing"


def command_inspect(arguments) -> int:
    engine = engine_for_env()
    try:
        return inspect_account(engine, arguments)
    finally:
        engine.dispose()


def inspect_account(engine, arguments) -> int:
    key = secret_key()
    clerk = fetch_clerk_user(key, arguments.clerk_user_id)
    email, verified = primary_email(clerk)
    print(f"Database : {describe_database(engine)}")
    print(f"Clerk key: {key.split('_')[1] if '_' in key else '?'} instance (sk_{key.split('_')[1] if '_' in key else '?'}_...)")
    print("\nClerk says this account is:")
    print(f"  id          {clerk.get('id')}")
    print(f"  name        {clerk.get('first_name') or ''} {clerk.get('last_name') or ''}".rstrip())
    print(f"  email       {email}  ({'verified' if verified else 'NOT VERIFIED'})")
    created = clerk.get("created_at")
    last = clerk.get("last_sign_in_at")
    print(f"  created     {datetime.fromtimestamp(created / 1000, UTC):%Y-%m-%d %H:%M} UTC" if created else "  created     ?")
    print(f"  last sign-in {datetime.fromtimestamp(last / 1000, UTC):%Y-%m-%d %H:%M} UTC" if last else "  last sign-in never")
    with engine.connect() as connection:
        legacy = connection.execute(select(User).where(User.id == LEGACY_USER_ID)).first()
        candidate = connection.execute(select(User).where(User.clerk_user_id == arguments.clerk_user_id)).first()
        print("\nIn the database:")
        if legacy is None:
            print("  legacy user      MISSING: nothing to claim")
        else:
            print(f"  legacy user      {'unlinked (claimable)' if legacy.clerk_user_id is None else 'ALREADY LINKED to ' + legacy.clerk_user_id}")
            print(f"    owns           {rows_summary(owned_counts(connection, LEGACY_USER_ID))}")
        if candidate is None:
            print("  that Clerk id    has no account row yet (it appears the first time the owner signs in; that is fine)")
        else:
            print(f"  that Clerk id    has an account row (timezone {candidate.timezone}); owns {rows_summary(owned_counts(connection, candidate.id))}")
    print("\nCompare the name and email above with the person who will sign in. If they are not the owner, STOP.")
    return 0


def check_backup(connection, backup: Path) -> None:
    manifest_file = manifest_path(backup)
    if not backup.is_file() or not manifest_file.is_file():
        raise Refused("Provide --backup pointing at a backup file that has its .manifest.json beside it (see backup_postgres.py).")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if problems := verify_backup(backup, manifest):
        raise Refused("The backup does not verify: " + "; ".join(problems))
    age = datetime.now(UTC) - datetime.fromisoformat(manifest["created_at_utc"])
    if age > MAX_BACKUP_AGE:
        raise Refused(f"The backup is {int(age.total_seconds() // 60)} minutes old (limit 60). Take a fresh one.")
    changed = [
        f"{name}: {now} rows now, {manifest['tables'][name]['rows']} in the backup"
        for name, now in table_totals(connection).items()
        if name != "users" and now != manifest["tables"].get(name, {}).get("rows")
    ]
    if changed:
        raise Refused("The database changed since the backup (" + "; ".join(changed) + "). Take a fresh backup.")


def plan_claim(connection, arguments) -> dict:
    """Check every precondition and return what would happen. Raises Refused if anything is off."""
    clerk = fetch_clerk_user(secret_key(), arguments.clerk_user_id)
    key_instance = "live" if secret_key().startswith("sk_live_") else "test" if secret_key().startswith("sk_test_") else "unknown"
    if key_instance != arguments.instance:
        raise Refused(f"You said the {arguments.instance} instance but CLERK_SECRET_KEY belongs to the {key_instance} one.")
    email, verified = primary_email(clerk)
    if not email or email.lower() != arguments.expect_email.lower():
        raise Refused(f"Clerk reports this account's email as {email!r}, not the expected {arguments.expect_email!r}.")
    if not verified:
        raise Refused(f"Clerk has not verified {email}; anyone could have registered it.")
    legacy = connection.execute(select(User).where(User.id == LEGACY_USER_ID)).first()
    if legacy is None:
        raise Refused("The legacy user does not exist in this database; there is nothing to claim.")
    if legacy.clerk_user_id is not None:
        raise Refused(f"The legacy user is already linked to {legacy.clerk_user_id}.")
    candidate = connection.execute(select(User).where(User.clerk_user_id == arguments.clerk_user_id)).first()
    if candidate is not None:
        if owned := owned_counts(connection, candidate.id):
            raise Refused(f"The account for {arguments.clerk_user_id} already owns data ({rows_summary(owned)}); refusing to replace it.")
        if arguments.timezone is None:
            raise Refused("That account already has settings: choose whose timezone to keep with --timezone legacy|account.")
    check_backup(connection, Path(arguments.backup).expanduser())
    return {
        "legacy_owns": owned_counts(connection, LEGACY_USER_ID), "email": email, "candidate": candidate,
        "timezone": (candidate.timezone if candidate is not None and arguments.timezone == "account" else legacy.timezone),
        "totals": table_totals(connection),
    }


def command_claim(arguments) -> int:
    engine = engine_for_env()
    try:
        return run_claim(engine, arguments)
    finally:
        engine.dispose()


def run_claim(engine, arguments) -> int:
    try:
        with engine.connect() as connection:
            plan = plan_claim(connection, arguments)
    except Refused as why:
        print(f"REFUSED (nothing was changed): {why}")
        return 1
    print(f"Database   : {describe_database(engine)}")
    print(f"Account    : {arguments.clerk_user_id}  ({plan['email']}, verified by Clerk, {arguments.instance} instance)")
    print(f"Will link  : the legacy user, which owns {rows_summary(plan['legacy_owns'])}")
    print(f"Empty account row: {'will be ' + ('left in place, unlinked' if arguments.unlink_empty else 'removed') if plan['candidate'] is not None else 'none exists yet'}")
    print(f"Timezone   : {plan['timezone']}")
    print("Data rows are not moved, copied or deleted.")
    if not arguments.execute:
        print("\nDry run: all checks passed. Re-run with --execute --confirm-clerk-id <id> to apply.")
        return 0
    if arguments.confirm_clerk_id != arguments.clerk_user_id:
        print("REFUSED: --confirm-clerk-id must repeat the Clerk id exactly.")
        return 1
    with engine.begin() as connection:
        # Re-check inside the transaction that will write, with both rows locked.
        connection.execute(select(User).where(User.id == LEGACY_USER_ID).with_for_update())
        plan = plan_claim(connection, arguments)
        users = User.__table__
        if plan["candidate"] is not None:
            account = users.c.id == plan["candidate"].id
            if arguments.unlink_empty:
                connection.execute(update(users).where(account).values(clerk_user_id=None))
            else:
                connection.execute(delete(users).where(account, users.c.clerk_user_id == arguments.clerk_user_id))
        updated = connection.execute(
            update(users).where(users.c.id == LEGACY_USER_ID, users.c.clerk_user_id.is_(None))
            .values(clerk_user_id=arguments.clerk_user_id, timezone=plan["timezone"])
        ).rowcount
        if updated != 1:
            raise Refused("Expected to link exactly one user; rolling everything back.")
        after = table_totals(connection)
        expected = dict(plan["totals"])
        if plan["candidate"] is not None and not arguments.unlink_empty:
            expected["users"] -= 1
        if after != expected:
            raise Refused(f"Row counts changed unexpectedly ({after} vs {expected}); rolling everything back.")
    print(f"\nDone. The legacy data now belongs to {arguments.clerk_user_id}. Sign in as that account and check your books, notes, tasks and projects.")
    print("To undo: UPDATE users SET clerk_user_id = NULL WHERE id = '00000000-0000-0000-0000-000000000001';")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="read-only: show who Clerk says the account is, and what the database holds")
    inspect.add_argument("--clerk-user-id", required=True)
    inspect.set_defaults(run=command_inspect)
    claim = commands.add_parser("claim", help="link the legacy data to the verified Clerk account (dry run unless --execute)")
    claim.add_argument("--clerk-user-id", required=True)
    claim.add_argument("--expect-email", required=True, help="the owner's email; must match Clerk's verified primary email")
    claim.add_argument("--instance", required=True, choices=["live", "test"], help="which Clerk instance the owner signs in to")
    claim.add_argument("--backup", required=True, help="a verified backup under an hour old (see backup_postgres.py)")
    claim.add_argument("--timezone", choices=["legacy", "account"], help="needed when the new account already has settings: whose timezone to keep")
    claim.add_argument("--unlink-empty", action="store_true", help="leave the empty account row in place (unlinked) instead of removing it")
    claim.add_argument("--execute", action="store_true")
    claim.add_argument("--confirm-clerk-id")
    claim.set_defaults(run=command_claim)
    arguments = parser.parse_args()
    try:
        return arguments.run(arguments)
    except Refused as why:
        print(f"REFUSED: {why}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
