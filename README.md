# Executive Function App — MVP 0.1

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

Today keeps at most three manually selected priorities. Earlier unfinished work
is offered separately: nothing is marked failed, automatically carried forward,
or silently rescheduled. Calendar, Projects, and Notes & Books are explicitly
reserved for later milestones.

## Configuration and security

`.env.example` contains local development defaults, not production credentials.
Do not commit `.env`. The MVP has **no real authentication**: requests use one
fixed development user, and all queries are scoped to that user. It is not safe
to expose either server publicly, even behind a publicly accessible preview URL.
The backend refuses production operation until real authentication is added.

- `APP_ENV=development`: explicitly enables the development-only context.
- `DATABASE_URL`: SQLAlchemy PostgreSQL URL using the `psycopg` driver.
- `USER_TIMEZONE`: initial IANA timezone, such as `America/New_York` or `UTC`.
- `CORS_ORIGINS`: comma-separated local frontend origins.
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

## Structure

- `frontend/`: React, TypeScript, Vite, Tailwind, shadcn/ui-style accessible
  components, Lucide icons, React Router, and TanStack Query.
- `backend/`: FastAPI, Pydantic, SQLAlchemy 2, Alembic migrations, and pytest.
- `docker-compose.yml`: loopback-only PostgreSQL with persistent storage.

## Remaining work, in priority order

1. Real authentication, production authorization, deployment hardening, and a
   reviewed backup/restore procedure before any public deployment.
2. Projects and their ownership-aware foreign keys; the nullable task project
   identifier is reserved for that milestone, not a working project module.
3. Calendar events with appointment times, notes, and the reading library.
4. Broader accessibility, mobile, and end-to-end regression coverage.

No AI services, paid APIs, streaks, or productivity penalties are included.