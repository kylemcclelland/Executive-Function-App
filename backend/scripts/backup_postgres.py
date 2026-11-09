# ruff: noqa: E501
"""Back up the production PostgreSQL database to a verified, self-contained SQLite file.

    export DATABASE_URL='postgresql+psycopg://...?sslmode=require'      # never on the command line
    python scripts/backup_postgres.py backup --out ~/optima-pars-backups --keep 12
    python scripts/backup_postgres.py verify ~/optima-pars-backups/optima-pars-20261109T180000Z.sqlite

What it does
  * reads the whole database in ONE read-only, repeatable-read transaction, so every table comes from
    the same instant even while the app is running; the database is never written to;
  * writes a SQLite file with the same schema and Alembic revision, plus a manifest holding the row
    count and a SHA-256 digest of every table and of the file itself (no password, no secret);
  * re-reads the finished file and checks it against the live data before keeping it, so a backup
    that cannot be trusted is never left lying around (it is written as ``*.partial`` and only
    renamed into place after it verifies);
  * optionally prunes the oldest backups it created, only after the new one has verified.

Restoring is the same copy tool used for the migration, into an EMPTY, migrated database:

    python -m alembic upgrade head        # against the empty target
    python scripts/sqlite_to_postgres.py --source BACKUP.sqlite --target "$TARGET_URL" --keep-clerk-users
    python scripts/sqlite_to_postgres.py ... --keep-clerk-users --execute

(``--keep-clerk-users`` matters here: a backup of production contains real, linked accounts.)

A backup contains personal data and encrypted Google tokens. Keep it somewhere private; never commit it.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine, event, select, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlite_to_postgres import alembic_revision, table_digest  # noqa: E402

from app.db import Base  # noqa: E402
from app.models import User  # noqa: E402,F401  (importing the models registers every table)

BATCH = 500
PATTERN = re.compile(r"^optima-pars-\d{8}T\d{6}Z\.sqlite$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sqlite_engine(path: Path, *, read_only: bool = False):
    target = f"file:{path.as_posix()}?mode={'ro' if read_only else 'rwc'}&uri=true"
    engine = create_engine(f"sqlite+pysqlite:///{target}")
    return engine


def database_url(arguments) -> str:
    url = os.environ.get(arguments.url_env, "")
    if not url:
        raise SystemExit(f"Set {arguments.url_env} to the PostgreSQL URL (it is not accepted on the command line).")
    if make_url(url).get_backend_name() != "postgresql":
        raise SystemExit("This tool backs up PostgreSQL only. The local SQLite file is never touched by it.")
    return url


def write_backup(url: str, destination: Path) -> dict:
    """Snapshot PostgreSQL into ``destination`` (a new SQLite file) and return its manifest."""
    tables = Base.metadata.sorted_tables
    source = create_engine(url, pool_pre_ping=True)
    target = sqlite_engine(destination)

    @event.listens_for(target, "connect")
    def enforce_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(target)
    manifest_tables: dict[str, dict] = {}
    with source.connect().execution_options(isolation_level="REPEATABLE READ") as src:
        src.execute(text("SET TRANSACTION READ ONLY"))  # a backup must never be able to write
        revision = alembic_revision(src)
        if revision is None:
            raise SystemExit("The database has no alembic_version table: refusing to back up an unmigrated database.")
        server = src.execute(text("SHOW server_version")).scalar()
        with target.begin() as dst:
            dst.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
            dst.execute(text("INSERT INTO alembic_version VALUES (:revision)"), {"revision": revision})
            for table in tables:
                result = src.execute(select(table))
                while batch := result.fetchmany(BATCH):
                    dst.execute(table.insert(), [dict(row._mapping) for row in batch])
        # Digests of what PostgreSQL held in this same snapshot, to compare against the file.
        for table in tables:
            rows, digest = table_digest(src, table)
            manifest_tables[table.name] = {"rows": rows, "sha256": digest}
    source.dispose()
    target.dispose()
    parsed = make_url(url)
    return {
        "format": 1,
        "created_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": {"host": parsed.host, "database": parsed.database, "server_version": server},
        "alembic_revision": revision,
        "tables": manifest_tables,
    }


def verify_backup(path: Path, manifest: dict) -> list[str]:
    """Everything wrong with a backup file, or an empty list if it matches its manifest exactly."""
    problems: list[str] = []
    expected_file = manifest.get("file", {})
    if expected_file:
        if path.stat().st_size != expected_file.get("bytes"):
            problems.append("file size differs from the manifest")
        if sha256_file(path) != expected_file.get("sha256"):
            problems.append("file SHA-256 differs from the manifest (the file changed after it was written)")
    engine = sqlite_engine(path, read_only=True)
    try:
        with engine.connect() as connection:
            if connection.execute(text("PRAGMA integrity_check")).scalar() != "ok":
                problems.append("SQLite integrity check failed")
            if connection.execute(text("PRAGMA foreign_key_check")).fetchall():
                problems.append("foreign key violations found")
            if alembic_revision(connection) != manifest["alembic_revision"]:
                problems.append("Alembic revision differs from the manifest")
            for table in Base.metadata.sorted_tables:
                want = manifest["tables"].get(table.name)
                if want is None:
                    problems.append(f"{table.name}: missing from the manifest")
                    continue
                rows, digest = table_digest(connection, table)
                if (rows, digest) != (want["rows"], want["sha256"]):
                    problems.append(f"{table.name}: contents differ from the manifest ({rows} rows, expected {want['rows']})")
    finally:
        engine.dispose()
    return problems


def manifest_path(path: Path) -> Path:
    return path.with_suffix(".manifest.json")


def prune(directory: Path, keep: int, newest: Path) -> list[Path]:
    backups = sorted((p for p in directory.iterdir() if PATTERN.match(p.name)), reverse=True)
    removed = []
    for old in backups[keep:]:
        if old == newest:
            continue
        old.unlink()
        manifest_path(old).unlink(missing_ok=True)
        removed.append(old)
    return removed


def command_backup(arguments) -> int:
    url = database_url(arguments)
    directory = Path(arguments.out).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    name = f"optima-pars-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.sqlite"
    final, partial = directory / name, directory / f"{name}.partial"
    if final.exists():
        print(f"{final} already exists; wait a second and retry.")
        return 1
    partial.unlink(missing_ok=True)
    try:
        manifest = write_backup(url, partial)
        problems = verify_backup(partial, manifest)
        if problems:
            print("The new backup did not verify, so it was discarded:\n  - " + "\n  - ".join(problems))
            return 1
        manifest["file"] = {"name": name, "bytes": partial.stat().st_size, "sha256": sha256_file(partial)}
        partial.replace(final)
        manifest_path(final).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        try:
            final.chmod(0o600)
            manifest_path(final).chmod(0o600)
        except OSError:
            pass  # not every filesystem supports POSIX modes
    finally:
        partial.unlink(missing_ok=True)
    print(f"Backup written and verified: {final}")
    print(f"  revision {manifest['alembic_revision']}, {sum(t['rows'] for t in manifest['tables'].values())} rows in {len(manifest['tables'])} tables")
    for table, info in manifest["tables"].items():
        if info["rows"]:
            print(f"    {table:<30}{info['rows']:>7}")
    print(f"  SHA-256 {manifest['file']['sha256']}")
    if arguments.keep:
        for old in prune(directory, arguments.keep, final):
            print(f"  pruned older backup {old.name}")
    return 0


def command_verify(arguments) -> int:
    path = Path(arguments.backup).expanduser().resolve()
    manifest_file = manifest_path(path)
    if not path.is_file() or not manifest_file.is_file():
        print(f"Need both {path.name} and {manifest_file.name}.")
        return 2
    problems = verify_backup(path, json.loads(manifest_file.read_text(encoding="utf-8")))
    if problems:
        print("BACKUP DOES NOT VERIFY:\n  - " + "\n  - ".join(problems))
        return 1
    print(f"OK: {path.name} matches its manifest (file digest, integrity, foreign keys and every table).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup", help="take a verified backup of the PostgreSQL database")
    backup.add_argument("--out", default="~/optima-pars-backups", help="directory for backups (kept private, outside the repository)")
    backup.add_argument("--keep", type=int, default=12, help="keep this many newest backups (0 keeps all)")
    backup.add_argument("--url-env", default="DATABASE_URL", help="environment variable holding the PostgreSQL URL")
    backup.set_defaults(run=command_backup)
    verify = commands.add_parser("verify", help="check a backup file against its manifest")
    verify.add_argument("backup", help="path to optima-pars-*.sqlite (its .manifest.json must sit beside it)")
    verify.set_defaults(run=command_verify)
    arguments = parser.parse_args()
    return arguments.run(arguments)


if __name__ == "__main__":
    sys.exit(main())
