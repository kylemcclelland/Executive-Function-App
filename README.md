# Optima Pars — MVP 0.1

*Unum est necessarium.* An executive-function workspace (repository: Executive-Function-App).

A calm, local-first-in-use workspace for remembering, planning, and doing.
Capture a thought without categorizing it, turn it into a task, and choose up to
three priorities for today. Data is stored in PostgreSQL, not browser storage.

## Requirements

- Python 3.12+
- Node.js 22.12+ (or a newer supported LTS release) and npm
- Docker with Docker Compose

## Local setup

Run these commands from the repository root.

```bash
cp .env.example .env
docker compose up -d --wait db
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.lock
python -m pip install -e './backend[dev]'
cd backend
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

In another terminal:

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open **http://127.0.0.1:5173**. The Vite development server proxies `/api`
requests to the backend. API documentation is at
**http://127.0.0.1:8000/docs**.

The database uses a named Docker volume. Browser refreshes and server restarts
do not remove data. `docker compose down` stops the database without removing
the volume; **`docker compose down -v` permanently deletes local data**.

If port 5432 is already occupied, change the host port in `docker-compose.yml`
and the port in `.env`'s `DATABASE_URL` together.

## Using the MVP

1. Capture something from Today or Inbox.
2. Refresh the browser to see the saved capture.
3. Convert it to a task. The original capture remains available.
4. Open Tasks, add a concrete next action, and optionally add small steps.
5. Select the task for Today. This does not change its deadline or scheduled date.
6. Complete it from Today or Tasks. Completed tasks can be reopened.

Converted inbox captures retain their original text and become read-only; edit
the resulting task instead. They can still be archived, restored, or deleted.
Deleting a task does not delete its source capture, and retrying conversion
cannot create a duplicate task.

Today keeps at most three manually selected priorities. Earlier unfinished work
is offered separately: nothing is marked failed, automatically carried forward,
or silently rescheduled. Calendar, Projects, and Notes & Books are explicitly
reserved for later milestones.

## Configuration and security

`.env.example` contains local development defaults, not production credentials.
Do not commit `.env` or `frontend/.env.local`. Every API endpoint except `/health`
requires a Clerk session token, verified on the server; see
[Authentication (Clerk)](#authentication-clerk). Data is scoped to the verified
Clerk user, and there is no development bypass or default user.

- `APP_ENV=development`: explicitly enables the development-only context.
- `DATABASE_URL`: SQLAlchemy PostgreSQL URL using the `psycopg` driver.
- `POSTGRES_PASSWORD`: also supplies the local connection password when the
  database URL does not include one.
- `USER_TIMEZONE`: initial IANA timezone, such as `America/New_York` or `UTC`.
- `CORS_ORIGINS`: comma-separated local frontend origins.
- `CLERK_SECRET_KEY` and/or `CLERK_JWT_KEY`, `CLERK_AUTHORIZED_PARTIES`: see below.
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`: Docker database settings.
  Keep these consistent with `DATABASE_URL`.

Timestamps represent UTC instants. Due dates, scheduled dates, and daily priority
dates are date-only values, not appointment times. Changing a timezone does not
rewrite historical dates. Appointment times and calendar events are out of scope.

### Supabase PostgreSQL

For private local development against Supabase, set `DATABASE_URL` to your
Supabase PostgreSQL connection string, replace its scheme with
`postgresql+psycopg://`, and require TLS with `?sslmode=require` (or
`&sslmode=require` when the URL already has query parameters). URL-encode special
characters in the password. Prefer a direct connection or session-mode pooler
for migrations. Run `alembic upgrade head` from `backend` as above.
Do not expose database credentials to the frontend. This uses PostgreSQL directly;
it does not implement Supabase Auth or claim Supabase RLS provides API ownership.

## Authentication (Clerk)

Sign-in and sign-up use [Clerk](https://clerk.com). The frontend (`@clerk/react`)
sends the session token as `Authorization: Bearer ...`; the backend verifies its
signature, expiry and `azp` with Clerk's `clerk-backend-api` and takes the user from
the verified `sub` claim only. Cookies, request bodies, query strings and custom
headers are never treated as identity. Users are matched by `users.clerk_user_id`;
a new Clerk account gets a new, empty account. Data created before authentication
belongs to a legacy user with no Clerk link, so no sign-up can see it until the owner
claims it deliberately: see [docs/clerk-data-migration-plan.md](docs/clerk-data-migration-plan.md).

### Clerk dashboard setup

Menu names change over time; the settings, not the labels, are what matter.

1. Create an application at <https://dashboard.clerk.com> and choose the sign-in
   methods you want (email, Google, ...).
2. **API keys**: copy the *Publishable key* into `frontend/.env.local` as
   `VITE_CLERK_PUBLISHABLE_KEY` (see `frontend/.env.example`). Copy the *Secret key*
   into the repository-root `.env` as `CLERK_SECRET_KEY`. Alternatively set
   `CLERK_JWT_KEY` to the instance's PEM public key to verify tokens without any
   network call. The secret key never goes in `frontend/`.
3. **Paths**: use your own application's pages, not the hosted Account Portal:
   sign-in `/sign-in`, sign-up `/sign-up`. The app already passes these (and `/` as
   the post-login destination and `/sign-in` after sign-out) to Clerk.
4. **Origins**: a development instance accepts `http://localhost:5173`. Open the app
   at `localhost`; Clerk development instances are built around it and `127.0.0.1`
   may not work. The backend only accepts tokens whose `azp` is in
   `CLERK_AUTHORIZED_PARTIES` (default: `CORS_ORIGINS`, which already lists it).
5. **Restrict who can sign up** (recommended while this holds personal data): use an
   allowlist or disable public sign-ups and invite yourself. Open sign-up only ever
   yields empty accounts, but there is no reason to allow it yet.
6. Restart the backend after editing `.env`, and the Vite server after editing
   `frontend/.env.local`.

For production, create a Clerk *production* instance (`pk_live_...`/`sk_live_...`),
set `CLERK_AUTHORIZED_PARTIES` and `CORS_ORIGINS` to the exact HTTPS origin, and
serve the API over HTTPS. The backend refuses to start with `APP_ENV=production`
unless a Clerk key is configured.

Apply the additive migration with `alembic upgrade head` from `backend` (back up
the SQLite file first). It only adds `users.clerk_user_id`; it changes no rows.

## Google Calendar (optional)

Signed-in users can connect their own Google Calendar (read-only) from the Calendar page and see
upcoming events there and on Today. It is off unless the `GOOGLE_*` settings are present, and
Optima Pars never requires it. Setup, the OAuth flow, security properties, and what Google requires
before it can be offered beyond test users are in [docs/google-calendar.md](docs/google-calendar.md).

## Brand and theme

**Optima Pars** (*Unum est necessarium*, “one thing is necessary”; Luke 10:42). The artwork supplied
as `frontend/Logo.png` is the approved logo and is kept untouched. Web copies derived from it live in
`frontend/src/assets/brand/` (full lockup at two sizes, and an arch-only crop for the sidebar).
`frontend/public/favicon.svg` and the PNG icons are a separate, simplified drawing of the abbey and
bell tower with no lettering, so they stay legible at 16px. The lockup is shown unaltered on its own
ivory ground in both themes.

Light, Dark and System themes are chosen in **Preferences** (and flipped from the sun/moon button in
the header). The choice is stored in this browser's `localStorage` under `optima-pars-theme`; System
follows the operating system. A small inline script in `frontend/index.html` applies the theme before
first paint, so there is no flash. All colours are tokens at the top of `frontend/src/index.css`
(`:root` for light, `:root[data-theme="dark"]` for dark); a test keeps stray colour values out of the
rest of the stylesheet and checks the text contrast of every token pair.

## Structure

- `frontend/`: React, TypeScript, Vite, Tailwind, shadcn/ui accessible
  components, Lucide icons, React Router, and TanStack Query.
- `backend/`: FastAPI, Pydantic, SQLAlchemy 2, Alembic migrations, and pytest.
- `docker-compose.yml`: loopback-only PostgreSQL with persistent storage.

## Checks

With the Python environment activated, run the backend checks from `backend`:

```bash
ruff check .
pytest
```

Run the frontend checks from `frontend`:

```bash
npm run lint
npm run test
npm run build
```

The production build includes TypeScript compilation. PostgreSQL-specific test
configuration and the results verified for this milestone are recorded below.

### PostgreSQL-backed tests

The default pytest run uses an isolated, migrated SQLite database and skips
PostgreSQL-only concurrency cases. To exercise PostgreSQL too, create a separate
test database once, from the repository root:

```bash
docker compose exec -T db createdb -U executive executive_function_test
cd backend
set -a
source ../.env
set +a
PGPASSWORD="$POSTGRES_PASSWORD" \
  TEST_DATABASE_URL="postgresql+psycopg://executive@127.0.0.1:5432/executive_function_test" \
  pytest
```

This command assumes the example local username and port; adjust them if you
changed your local configuration. Tests migrate isolated schemas and remove
them afterward. Use a disposable test database, never a production connection.

### Verified for MVP 0.1

- PostgreSQL 17: **36 backend tests passed**, including ownership, concurrent
  conversion/priority updates, migration preservation, and commit-failure rollback.
- SQLite fallback: **34 passed, 2 PostgreSQL-only concurrency tests skipped**.
- Frontend: **28 interaction tests passed**, also run in Los Angeles and
  Kiritimati timezones; TypeScript, lint, and production build passed.
- Docker Compose startup, Alembic upgrade/schema checks, and actual API startup
  succeeded. Dependency advisory scans and frontend audit reported no findings.
- Manual browser verification completed the capture → refresh → conversion →
  next action → Today selection → completion → refresh flow against PostgreSQL.
  Original capture text and independent task dates remained preserved.

## Remaining work, in priority order

1. Claiming pre-authentication data for its owner's Clerk account (needs the
   owner's approval), deployment hardening, and a reviewed backup/restore
   procedure before any public deployment.
2. Projects and their ownership-aware foreign keys; the nullable task project
   identifier is reserved for that milestone, not a working project module.
3. Calendar events with appointment times, notes, and the reading library.
4. Broader accessibility, mobile, and end-to-end regression coverage.

No AI services, paid APIs, streaks, or productivity penalties are included.