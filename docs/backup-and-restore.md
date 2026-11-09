# Backing up and restoring the production database

The production data lives in Neon PostgreSQL. This is the repeatable procedure for backing it up, proving
the backup is good, and restoring it. It was exercised end to end against a real PostgreSQL 18 (see the
tests in `backend/tests/test_backup.py`). **The local SQLite database is never touched by any of it.**

## What a backup is
`backend/scripts/backup_postgres.py` writes one self-contained **SQLite file** (same schema, same Alembic
revision) plus a **manifest**:

```
optima-pars-20261109T180000Z.sqlite          the data
optima-pars-20261109T180000Z.manifest.json   per-table row counts and SHA-256 digests, the file's own SHA-256,
                                             Alembic revision, source host/database (no password, no secret)
```

Why this format: it needs no PostgreSQL client tools, it is verifiable by anyone with Python, it opens
in any SQLite browser, and it restores with the same tool used for the migration.

How it stays trustworthy:
- It reads the **whole database in one read-only, repeatable-read transaction**, so every table comes from the
  same instant even while the app is in use, and it cannot write to the database.
- It is written as `*.partial`, **re-read and compared with the live snapshot**, and only then renamed into
  place. A backup that fails verification is deleted, never left behind.
- `verify` re-checks any backup later: file digest, SQLite integrity, foreign keys, and every table value by value.

## Take a backup
Run from `backend/` on your machine (any machine with Python 3.12+ and `pip install -r requirements.lock`).
Put the connection string in the environment; it is deliberately not accepted as a command-line argument,
so it never appears in shell history or process lists.

```powershell
$env:DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@HOST/DB?sslmode=require"   # Neon direct connection
python scripts/backup_postgres.py backup --out "$HOME\optima-pars-backups" --keep 12
python scripts/backup_postgres.py verify "$HOME\optima-pars-backups\optima-pars-<timestamp>.sqlite"
```

`--keep 12` retains the newest twelve and prunes older ones, only after the new backup verified, and only
files that match `optima-pars-<timestamp>.sqlite` (nothing else in the folder is ever deleted).

**When to take one**
- Immediately **before every production migration** (including the data load) and before the ownership claim.
- **Weekly** otherwise (Windows Task Scheduler: weekly task running the two lines above; set `DATABASE_URL`
  from a protected user-level environment variable, not inside the task definition).
- Neon Free keeps only a 6-hour restore window, so these backups are your real safety net.

**Where to keep them:** a private, ideally encrypted location (an encrypted drive, or a private cloud folder
you trust). A backup holds all your notes, tasks and library plus encrypted Google tokens. Never commit one
(`.gitignore` blocks the filenames) and never put one in a public repository's CI artifacts.

## Restore
Restoring means loading a backup into an **empty, migrated** database: a new Neon branch or database is
ideal, so the damaged one stays available for inspection.

```powershell
$env:DATABASE_URL = "postgresql+psycopg://...NEW-EMPTY-DB...?sslmode=require"
python -m alembic upgrade head
python scripts/backup_postgres.py verify "<backup file>"                       # never restore an unverified file
python scripts/sqlite_to_postgres.py --source "<backup file>" --target $env:DATABASE_URL --keep-clerk-users
python scripts/sqlite_to_postgres.py --source "<backup file>" --target $env:DATABASE_URL --keep-clerk-users --execute
```

The first run is a dry run. The second copies in one transaction and then compares every table; the last
line must read **"Every table matches the source exactly."** `--keep-clerk-users` is essential for a restore:
a backup of production contains real, linked accounts. Then point the backend's `DATABASE_URL` at the
restored database and redeploy.

## Restore drill (do it once before relying on this)
1. Take a backup and `verify` it.
2. Create an empty Neon branch, run `alembic upgrade head` against it, restore into it.
3. Start the backend locally against that branch and sign in: your library and tasks should be there.
4. Delete the branch.

The same drill runs automatically in the test suite against a disposable PostgreSQL
(`test_restoring_a_backup_reproduces_every_row_in_a_fresh_database`).

## Alternatives and limits
- **Neon restore / branching** restores within the plan's window (6 hours on Free, up to 7 days on Launch)
  without any tooling, and is the fastest way to undo a bad change. It is a convenience, not a substitute
  for your own backups.
- **`pg_dump -Fc`** is the standard PostgreSQL tool and is fine to use too (`pg_dump` must be at least as new as
  the server). It was not exercised in this project's environment, so the SQLite-format backup above is the
  tested, documented procedure.
- The tool backs up **PostgreSQL only** and refuses a SQLite URL, so it cannot be pointed at your local database by accident.
- A backup is as large as your data (a few megabytes today). Nothing here is designed for gigabytes.
