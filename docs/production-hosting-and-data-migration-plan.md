# Optima Pars: production hosting and data migration plan

**Status: proposal for review. Nothing in this plan has been deployed, migrated or merged.** The only
things done so far are the Vercel frontend preview (already reviewed), local rehearsals against a
*disposable* PostgreSQL that has since been deleted, and this document.

## 1. What I found in the backend

| Area | Finding | Consequence |
|---|---|---|
| Database layer | SQLAlchemy 2 + Alembic, psycopg 3 already a dependency. SQLite-only code is limited to `PRAGMA foreign_keys` (skipped on PostgreSQL) and portable partial indexes (`postgresql_where` set alongside `sqlite_where`). | PostgreSQL is a first-class target, not a port. |
| **Verified on PostgreSQL** | I ran the entire backend suite against a scratch PostgreSQL 18.6: **332 passed, 1 skipped** (SQLite: 331 passed, 2 skipped; the extra PG-only concurrency tests ran and passed). All nine migrations (0001 to 0009) also applied cleanly to an empty PostgreSQL. | Schema and queries are compatible. |
| Process state | Three things live in memory per process: the Goodreads **import preview store**, the Open Library request **pacer**, and the Google **access-token cache**. | The API must run as **one always-on process** (`--workers 1`). It rules out serverless functions (each request could land on a different instance and lose a pending import). The cover cooldown itself is persisted in the database, so restarts are safe. |
| Startup | `APP_ENV=production` refuses to start unless Clerk is configured. `/health` checks the database. No auto-migration at startup. | Run `alembic upgrade head` as a release step; point the platform health check at `/health`. |
| Config | Everything comes from environment variables (see section 4). No file-based config needed. | Straightforward on any container host. |
| Packaging | No Dockerfile today. `requirements.lock` is a Python 3.12 set (local venv is 3.14, tests pass on it). | Add a small Dockerfile on `python:3.12-slim`, install the lock, run uvicorn. |
| Open endpoints | FastAPI's `/docs`, `/redoc`, `/openapi.json` are public. They expose the API shape, not data. | Recommend disabling them when `APP_ENV=production` (one-line change, not yet made). |
| Auth | Every route except `/health` requires a verified Clerk session; the Google callback is authenticated by single-use `state`. | No change needed for hosting. |

## 2. Recommended hosting (simplest, reliable, inexpensive)

**Frontend: Vercel (already set up).  Backend: one small always-on container on Railway.
Database: Neon (managed PostgreSQL).**

```
Browser -> Vercel (static app, same origin)
              |  /api/*  rewrite (proxy)
              v
          Railway: FastAPI container, 1 process  --->  Neon PostgreSQL
```

Why this shape:
- **Same-origin API.** A Vercel rewrite sends `/api/*` to the backend, so the browser only ever talks to one
  host: no CORS surface, Clerk's `azp` check sees one origin, and the Google OAuth callback can be the
  Vercel URL.
- **Neon for data**, because it is a managed database independent of the app host (you can change
  hosts without touching data), with branches and point-in-time restore. Connect with `sslmode=require`;
  use the direct (non-pooled) endpoint so Alembic and psycopg behave normally.
- **Railway for the process**: GitHub-connected, environment variables in a dashboard, one service.

**Expected cost: about $5 a month**, from numbers I verified on the providers' pricing pages today:

| Piece | Plan | Cost | Notes |
|---|---|---|---|
| Railway | Hobby | $5/month including $5 usage credit; usage billed at roughly $10 per GB-month of memory and $20 per vCPU-month | A small idle-ish FastAPI container should sit inside the included credit. If usage exceeds $5, the whole usage is billed. |
| Neon | Free | $0: 1 GB storage (your database is a few MB), 100 compute-hours, suspends after 5 minutes idle (first query after idle takes a moment longer) | Free restore window is only **6 hours**. Launch is usage-based (7-day restore). |
| Vercel | Hobby | $0 | Already set up. |

I could not retrieve Render's or Railway's database pricing pages, so those are not quoted.

Alternatives considered:
- **Fly.io VM + Neon**: cheapest ($2.19 to $3.69 a month for 256 to 512 MB VMs), but needs the Fly CLI and
  config; Fly's own managed Postgres starts at $38 a month, so you would still use Neon.
- **Everything on Railway** (Postgres as a second Railway service): one dashboard, roughly $7 to $10 a month,
  but you own the database container, volume and backups.
- **Supabase**: free projects pause after a week of inactivity and Pro is $25 a month; not worth it for one app.
- **Backend on Vercel Functions**: tempting (same platform), but the in-memory import store makes it unsafe,
  as above.

**Backups (required either way).** Neon Free restores only 6 hours back, so take a `pg_dump` before every
migration and on a schedule (weekly is plenty for this app's change rate), stored privately outside the
database host. Upgrade to Neon Launch if you want a 7-day restore window.

## 3. Data inventory (the real database, read-only)

Source: `C:/Users/uvaga/Executive-Function-App/backend/data/executive_function.db` (the file `.env` points at; Alembic `0009`).

| Table | Rows | Plan |
|---|---|---|
| users | 2 | Copy the **legacy user** (owner of everything below). The second row is the **development-Clerk** account; do not copy (see 5.2). |
| books (your Goodreads library) | 2,170 | Copy, unchanged |
| notes / note_tags | 5 / 3 | Copy |
| tasks | 4 | Copy |
| projects / milestones / project notes / project updates | 3 / 1 / 1 / 1 | Copy |
| inbox_items | 2 | Copy |
| cover_lookups / cover_service_state | 22 / 2 | Copy (a cache; harmless either way) |
| daily_priorities, task_steps, note_links, work_sessions | 0 | nothing to copy |
| google_calendar_connections / google_oauth_states | 1 / 3 | **Not copied.** They belong to the development Clerk account and hold a token encrypted with a development key. Reconnect Google Calendar in production (one click). |

Every row of user data belongs to the legacy user `00000000-0000-0000-0000-000000000001`; ownership is
carried by `user_id` and parent foreign keys, all primary keys are UUIDs, so rows are copied verbatim and
every relationship survives.

## 4. Production configuration (names only; values stay in the hosts' secret stores)

Backend (Railway): `APP_ENV=production`, `DATABASE_URL` (Neon, `postgresql+psycopg://...?sslmode=require`),
`CLERK_SECRET_KEY` (production instance), `CLERK_AUTHORIZED_PARTIES` (the exact production origin),
`CORS_ORIGINS`, `FRONTEND_URL`, `USER_TIMEZONE`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
`GOOGLE_REDIRECT_URI` (`https://<production origin>/api/integrations/google-calendar/callback`),
`GOOGLE_TOKEN_ENCRYPTION_KEY` (a **new** key generated for production and backed up).

Frontend (Vercel): only `VITE_CLERK_PUBLISHABLE_KEY` (the production publishable key). The Vercel project
currently also holds `CLERK_SECRET_KEY` and the `GOOGLE_*` values; a static frontend does not use them, so
move them to Railway and delete them from Vercel when the backend is set up.

Vercel `frontend/vercel.json` gains one rewrite, **before** the single-page-app catch-all:
`{ "source": "/api/:path*", "destination": "https://<railway-domain>/api/:path*" }`.

Draft container (not yet added to the repository):

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.lock backend/pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.lock
COPY backend/ ./
RUN pip install --no-cache-dir --no-deps .
# One process on purpose: the import-preview store and request pacer are per-process.
CMD ["sh", "-c", "python -m alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
```

(Running Alembic at start is safe here because there is only ever one instance and every migration so far is
additive; if you prefer, make it a separate release command.)

## 5. Migration plan

### 5.1 Already rehearsed (disposable local PostgreSQL, since deleted)
I copied the real database to a scratch file, built an empty PostgreSQL schema with Alembic, and ran the new
copy script `backend/scripts/sqlite_to_postgres.py`. The script is **dry-run by default**, opens the source
read-only, refuses a target that is not empty or not at the same Alembic revision, copies everything in
**one transaction**, then re-reads every table from both databases and compares them value for value.
Result: **all 18 tables identical** (2,170 books, 5 notes, 4 tasks, 3 projects and the rest). A second run
refused to touch the now-populated target. I then rehearsed the ownership claim on that scratch copy and
confirmed, through the real API on PostgreSQL, that the owner sees all 2,170 books, 4 tasks, 3 projects,
5 notes and 2 inbox items, and that a different signed-in user sees none of it.

### 5.2 Why development Clerk accounts are left behind
A Clerk development instance and a production instance have **separate user ids**. A row linked to a
development id can never match a production sign-in, so it is dead weight. The script skips such users only
when they own nothing but the Google credential rows described above, and stops if they own anything else.

### 5.3 Steps (each waits for your explicit go-ahead)
1. **Prepare (no data).** Create the Neon project and Railway project; add the Dockerfile; set environment
   variables; create the Clerk **production** instance and Google redirect URI (see 6). Deploy the backend
   against the **empty** Neon database. Smoke-test `/health` and sign-in. Nothing from your real data yet.
2. **Freeze.** Stop the local backend on 8001 so the SQLite file stops changing.
3. **Back up.** SQLite online backup of the database to a dated file plus its SHA-256; Neon restore point
   (branch) before loading.
4. **Load.** `python -m alembic upgrade head` against Neon, then
   `sqlite_to_postgres.py --source <backup> --target <neon url>` (dry run first, then `--execute`). Required
   outcome: "Every table matches the source exactly."
5. **Owner sign-in.** You sign in to production once, which creates an empty account for your production
   Clerk id.
6. **Claim (separate, explicitly approved).** In one transaction: confirm that account owns nothing, remove or
   unlink it, and set the legacy user's `clerk_user_id` to your production Clerk id, exactly as written in
   `docs/clerk-data-migration-plan.md` section 3. Verify through the app; verify a second throwaway account
   sees nothing.
7. **Reconnect Google Calendar** in production.
8. **Cut over.** Promote the frontend to production only after 1 to 7 pass.

**Rollback.** The SQLite file is never modified, so the local app keeps working at every step. If loading
or verification fails, drop the Neon database (or restore the branch) and repeat; nothing else depends on it.

## 6. Blockers and decisions for you

1. **A domain you own.** As I understand Clerk's and Google's rules (please confirm on their docs), a Clerk
   *production* instance requires your own domain (not `*.vercel.app`), and Google verification needs a
   verified domain plus a privacy policy. Until then, Clerk stays on its development instance and Google stays
   in Testing (test users only). Decide whether to buy a domain now.
2. **Approve the hosting choice** (Railway + Neon + Vercel, about $5/month), or pick an alternative above.
3. **The four open ownership questions** from `docs/clerk-data-migration-plan.md`: your production Clerk
   user id (only exists after step 5), whether the claim may delete the empty auto-created row, which timezone
   wins, and a standing backup step. The canonical database is settled: the one `.env` points at; the repo's
   own `backend/data/executive_function.db` is a stale copy and should be retired.
4. **Disable `/docs` in production** (small code change) and **add the Dockerfile and rewrite**; I have not made
   these yet.
5. **Housekeeping:** the stray `clerk-react/` scaffold is committed to the branch (`.vercelignore` keeps it out
   of Vercel uploads); consider removing it.

## 7. Operational notes
- Run Alembic as `python -m alembic ...`; the `alembic.exe` launcher in the local venv once failed to find an installed package.
- Keep one backend instance. If you ever need more, first move the import-preview store into the database.
- Rotate `GOOGLE_TOKEN_ENCRYPTION_KEY` by putting the new key first and keeping the old one (`new,old`).
