# ruff: noqa: E501
"""Copy an Optima Pars SQLite database into an empty, migrated PostgreSQL database.

    python scripts/sqlite_to_postgres.py --source data/executive_function.db --target "$DATABASE_URL"

By default this is a DRY RUN: it reads the source (read-only), checks the target and reports what it
would copy. Nothing is written unless --execute is given. It never modifies the source.

Safety rules, enforced in code:
  * the source is opened read-only and must be at the same Alembic revision as the target;
  * the target must already be migrated (``alembic upgrade head``) and every table must be EMPTY;
  * rows are copied unchanged, primary keys and ownership included, so every relationship survives;
  * the whole copy is one transaction: any failure leaves the target untouched;
  * afterwards every table is re-read from both databases and compared value for value.

Users that are linked to a Clerk account are NOT copied by default (``--keep-clerk-users`` copies
them). A development Clerk instance and a production Clerk instance have different user ids, so a
dev-linked row would never match a production sign-in. The script refuses to skip such a user if
any data belongs to it. The legacy, unlinked user is always copied: it is what owns the existing data.
"""

import argparse
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, select, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.db import Base  # noqa: E402
from app.models import User  # noqa: E402,F401  (importing the models registers every table)

BATCH = 500
# Credentials and in-flight sign-in attempts tied to a development Clerk account. They cannot be
# used by another Clerk instance (and the encryption key may differ), so they are left behind and
# the owner simply reconnects Google Calendar in production.
LEFT_BEHIND = {"google_calendar_connections", "google_oauth_states"}


def alembic_revision(connection) -> str | None:
    try:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:
        return None


def canonical(value):
    """A stable text form of a column value, so SQLite and PostgreSQL rows compare equal."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (date, UUID)):
        return str(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return repr(value)


def table_digest(connection, table, where=None) -> tuple[int, str]:
    statement = select(table)
    if where is not None:
        statement = statement.where(where)
    keys = [column.name for column in table.primary_key.columns] or [
        column.name for column in table.columns
    ]
    rows = sorted(
        (
            tuple(canonical(row._mapping[column.name]) for column in table.columns)
            for row in connection.execute(statement)
        ),
        key=lambda row: tuple(row[[c.name for c in table.columns].index(key)] for key in keys),
    )
    digest = hashlib.sha256()
    for row in rows:
        digest.update("\x1f".join(row).encode())
        digest.update(b"\x1e")
    return len(rows), digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--source", required=True, help="path to the SQLite database file")
    parser.add_argument(
        "--target", required=True, help="SQLAlchemy URL of the migrated PostgreSQL database"
    )
    parser.add_argument(
        "--execute", action="store_true", help="actually copy (default is a dry run)"
    )
    parser.add_argument(
        "--keep-clerk-users", action="store_true", help="also copy users linked to a Clerk account"
    )
    parser.add_argument(
        "--allow-empty-accounts",
        action="store_true",
        help="allow the target to already hold Clerk account rows (made by signing in) that own "
        "nothing; they are left untouched. Every other table must still be empty.",
    )
    args = parser.parse_args()

    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        print(f"Source not found: {source_path}")
        return 2
    target_url = make_url(args.target)
    if target_url.get_backend_name() != "postgresql":
        print("The target must be a PostgreSQL URL (postgresql+psycopg://...)")
        return 2

    # Read-only source: the file cannot be changed through this connection.
    source = create_engine(f"sqlite+pysqlite:///file:{source_path.as_posix()}?mode=ro&uri=true")
    target = create_engine(args.target)
    tables = Base.metadata.sorted_tables

    with source.connect() as src, target.connect() as dst:
        source_revision, target_revision = alembic_revision(src), alembic_revision(dst)
        print(f"Source: {source_path}  (revision {source_revision})")
        print(
            f"Target: {target_url.render_as_string(hide_password=True)}  (revision {target_revision})"
        )
        if source_revision != target_revision or source_revision is None:
            print(
                "STOP: source and target must be at the same Alembic revision. Run `alembic upgrade head` on both."
            )
            return 1
        occupied = {
            t.name: n
            for t in tables
            if (n := dst.execute(select(text("count(*)")).select_from(t)).scalar())
        }
        preexisting: list[UUID] = []  # empty account rows already in the target, left untouched
        if occupied and args.allow_empty_accounts:
            accounts = list(dst.execute(select(User)))
            if occupied.get("users") == len(accounts) and all(a.clerk_user_id for a in accounts):
                preexisting = [a.id for a in accounts]
                owned_by_accounts = {
                    t.name: n
                    for t in tables
                    if "user_id" in t.c
                    and (
                        n := dst.execute(
                            select(text("count(*)")).select_from(t).where(t.c.user_id.in_(preexisting))
                        ).scalar()
                    )
                }
                others = {k: v for k, v in occupied.items() if k != "users"}
                if not others and not owned_by_accounts:
                    occupied = {}
                    print(
                        f"Target holds {len(preexisting)} Clerk account row(s) that own nothing; "
                        "they will be left untouched."
                    )
        if occupied:
            print(
                f"STOP: the target is not empty: {occupied}. This script only fills an empty database"
                " (or one holding only empty Clerk account rows, with --allow-empty-accounts)."
            )
            return 1

        skipped_users: list[UUID] = []
        if not args.keep_clerk_users:
            skipped_users = [
                row.id for row in src.execute(select(User).where(User.clerk_user_id.is_not(None)))
            ]
        for user_id in skipped_users:
            owned = {
                t.name: n
                for t in tables
                if "user_id" in t.c
                and t.name not in LEFT_BEHIND
                and (
                    n := src.execute(
                        select(text("count(*)")).select_from(t).where(t.c.user_id == user_id)
                    ).scalar()
                )
            }
            if owned:
                print(
                    f"STOP: Clerk-linked user {user_id} owns data {owned}; refusing to skip it. Use --keep-clerk-users or review."
                )
                return 1
        if skipped_users:
            print(
                f"Skipping {len(skipped_users)} Clerk-linked user(s) that own no tasks, notes, books or projects"
            )
            print(
                f"(development-instance accounts), together with their rows in {sorted(LEFT_BEHIND)}."
            )

        def scoped(table):
            """The rows to copy: everything, minus the skipped users and what hangs off them."""
            if not skipped_users:
                return None
            if table is User.__table__:
                return User.id.not_in(skipped_users)
            if "user_id" in table.c and table.name in LEFT_BEHIND:
                return table.c.user_id.not_in(skipped_users)
            return None

        plan = {}
        for table in tables:
            statement = select(table)
            if (where := scoped(table)) is not None:
                statement = statement.where(where)
            plan[table.name] = (
                table,
                statement,
                src.execute(select(text("count(*)")).select_from(statement.subquery())).scalar(),
            )
        clash = {
            row.clerk_user_id
            for row in src.execute(select(User).where(User.clerk_user_id.is_not(None)))
            if (row.id not in skipped_users)
        } & {
            a.clerk_user_id for a in dst.execute(select(User).where(User.id.in_(preexisting)))
        }
        if clash:
            print(f"STOP: the source would copy a Clerk account the target already has: {clash}")
            return 1
        scoped_filters = {name: scoped(plan[name][0]) for name in plan}
        width = max(len(name) for name in plan)
        for name, (_, _, count) in plan.items():
            print(f"  {name:<{width}}  {count:>6} rows")
        if not args.execute:
            print("\nDry run only. Re-run with --execute to copy.")
            return 0

    with source.connect() as src, target.begin() as dst:
        for name, (table, statement, expected) in plan.items():
            copied = 0
            result = src.execute(statement)
            while batch := result.fetchmany(BATCH):
                dst.execute(table.insert(), [dict(row._mapping) for row in batch])
                copied += len(batch)
            assert copied == expected, f"{name}: expected {expected}, copied {copied}"
        print("\nCopied in one transaction. Verifying every table value by value...")

    failures = 0
    with source.connect() as src, target.connect() as dst:
        for name, (table, statement, expected) in plan.items():
            where = scoped_filters[name]
            source_count, source_digest = table_digest(src, table, where)
            target_where = (
                User.id.not_in(preexisting) if preexisting and table is User.__table__ else None
            )
            target_count, target_digest = table_digest(dst, table, target_where)
            ok = source_count == target_count == expected and source_digest == target_digest
            failures += not ok
            print(
                f"  {'OK  ' if ok else 'FAIL'} {name:<{width}} {target_count:>6} rows  {target_digest[:12]}"
            )
    if failures:
        print(
            f"\n{failures} table(s) differ. The target should be dropped and recreated before another attempt."
        )
        return 1
    print("\nEvery table matches the source exactly.")
    if preexisting:
        print(f"{len(preexisting)} existing empty account row(s) in the target were left untouched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
