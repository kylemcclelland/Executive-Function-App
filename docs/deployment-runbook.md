# Deployment runbook: Vercel + Railway + Neon

Approved architecture: **Vercel** (frontend) + **Railway** (one FastAPI container) + **Neon** (PostgreSQL).
Nothing below has been executed. Each numbered step in "Stage 1" needs your explicit go-ahead.

## 0. Current status: Stage 1 private staging is live (2026-11-09)

| Piece | Where | State |
|---|---|---|
| Frontend | Vercel project `optima-pars`; staging URL `https://optima-pars-git-copilot-build-mvp-0-1-kyle-f16c.vercel.app` (branch alias of `copilot/build-mvp-0-1`) | Deployment Protection is **on for all deployments, including the production alias** |
| Backend | Railway project `optima-pars-staging`, service `api` (one replica), public API host `https://api-production-1a18.up.railway.app` | Image built from `backend/Dockerfile`; migrations 0001 to 0009 applied on first start |
| Database | Neon project `optima-pars-staging` (id `summer-snow-16078087`, AWS us-east-1, PostgreSQL 18, Free plan, direct connection, `sslmode=require`) | **Empty**: no SQLite data has been migrated |
| Auth | Clerk **development** instance; sign-ups restricted to one allowlisted email | A non-allowlisted sign-up is refused |

Verified on staging with a temporary Clerk test user (since deleted): signed-out visitors are sent to `/sign-in` and the app makes no API calls; a Clerk-signed session reaches Today, Tasks, Inbox, Projects, Calendar, Library, Notes and Preferences with every API call returning 200; calls without a token return 401; a new account gets the timezone `America/New_York`. Browser-visible API paths all go through the Vercel `/api` rewrite.

**Use the branch alias, not `optima-pars.vercel.app`, until the branch is merged.** The production alias serves the
last build of `main` (commit `52b17d0`), which predates `frontend/vercel.json`. With no rewrites, every `/api/*`
call is answered by Vercel itself with `404 NOT_FOUND` (`x-vercel-error: NOT_FOUND`, even though a valid Clerk bearer
token is sent), so Today's Priorities, Tasks, Projects, Notes and Library all fail, and direct loads of `/tasks`,
`/sign-in` and so on 404 too. Nothing is wrong with the backend or the frontend code. Merging the branch (or its
`frontend/vercel.json`) into `main` fixes that alias with no other change; Deployment Protection stays on either way.
Also: Clerk's own sign-in screens still say "Studium" because that is the application name in the Clerk dashboard; rename it there.

**Every browser origin that serves the app must be listed in Railway's `CLERK_AUTHORIZED_PARTIES`** (comma-separated). A Clerk session token
carries the origin it was issued for (`azp`); the backend rejects a valid, unexpired token from any other origin with `401 Authentication required`,
and logs `Rejected session token: token-invalid-authorized-parties (token origin '...' is not in CLERK_AUTHORIZED_PARTIES)` (Railway logs).
Currently listed: `https://optima-pars.vercel.app` and the branch alias `https://optima-pars-git-copilot-build-mvp-0-1-kyle-f16c.vercel.app`.
Per-deployment URLs (`optima-pars-<hash>-kyle-f16c.vercel.app`) are deliberately not listed, so a session there gets 401. Add a custom domain here too when you have one.

Known exposure: the Railway API host is public (Vercel cannot reach a private network). It serves only `/health` without a valid Clerk token issued for the staging origin, and it has no API docs. If you want it closed further, add an origin shared secret checked by the backend.

## 1. Can we start on the Vercel subdomain? (investigated)

**Short answer: yes for a private staging deployment, no for a real production launch.**

| Service | On `*.vercel.app` today | Needs your own domain for |
|---|---|---|
| **Clerk** | **Development instance only** (`pk_test_`/`sk_test_`). Clerk's docs say the dev-keys-on-your-host's-preview-domain setup is the easy option for Vercel, and that production keys currently cannot be used with a host-provided domain such as `*.vercel.app`. | A **production instance**: Clerk requires "a domain you own" and the ability to add DNS records (CNAMEs for the frontend API, account portal and email). |
| **Google Calendar OAuth** | **Works in Testing mode.** Redirect URIs must be HTTPS, exact (no wildcards), and their host must be on the Public Suffix List; I checked the live list and `vercel.app` **is** on it. So `https://optima-pars.vercel.app/api/integrations/google-calendar/callback` is an acceptable redirect URI. Limits in Testing: only listed test users (max 100); their authorization (and refresh token) **expires after 7 days**, so expect to reconnect weekly; users see an "unverified app" warning. | **Verification / public availability.** Google requires every authorized domain to be verified in Search Console, a homepage on that verified domain describing the app, and a privacy policy on the same domain. I could not confirm that a `*.vercel.app` subdomain can pass this (you cannot add DNS records at `vercel.app`); treat a custom domain as required. Unverified apps are also capped at 100 new users for the life of the project. |

What this means in practice:
- **Stage 1 (now): staging on the Vercel URL**, Clerk *development* instance, Google in *Testing* with you as the only test user. Private, single-user, fully functional, about $5/month. Clerk dev instances are "not suitable for production workloads", cap at 100 users, show a "Development" banner on Clerk screens, and carry a dev-browser token in the URL query string, which is why this stage must stay private (Vercel Deployment Protection on, sign-ups restricted).
- **Stage 2 (later): buy a domain** (a few dollars a year), put it on Vercel, create the Clerk production instance (DNS records), update Google (authorized domain, privacy policy, homepage, verification), and re-link your account (`docs/clerk-ownership-transfer-runbook.md`, "Two stages").
- Clerk states user data cannot be transferred between instances. Your data does not live in Clerk, only the id link does, so the move is one database column.

## 2. What is already prepared (committed to the repository)
| Piece | File | Notes |
|---|---|---|
| Production image | `backend/Dockerfile`, `backend/.dockerignore` | Python 3.12, locked dependencies without test tools, non-root user, runs `alembic upgrade head` then **one** uvicorn worker. Excludes `.env*`, databases, tests. |
| Variable templates | `backend/.env.production.example`, `frontend/.env.production.example` | Names and shapes only. |
| API proxy + security headers | `frontend/vercel.json` | `/api/*` rewrite (host is a placeholder until Railway exists), SPA fallback, nosniff, frame denial, referrer/permissions policies, HSTS, long-cache for hashed assets, and a **report-only** Content-Security-Policy. |
| Deploy gate | `frontend/scripts/check-deploy-config.mjs` (`npm run check:deploy`) | Fails while the rewrite points at the placeholder, or the CSP hash no longer matches the built page. |
| Backend hardening | `backend/app/core/config.py` (`production_problems`), `backend/app/main.py` | With `APP_ENV=production` startup **refuses** SQLite, a remote database without `sslmode=require`, missing Clerk key or `CLERK_AUTHORIZED_PARTIES`, any non-https/localhost/wildcard origin, partial Google settings. `/docs`, `/redoc`, `/openapi.json` are off. Every response gets nosniff, frame denial, no-referrer, a locked-down CSP and, in production, HSTS; `/api/*` is `Cache-Control: no-store`. |
| Backups | `backend/scripts/backup_postgres.py`, `docs/backup-and-restore.md` | Verified, repeatable, tested on PostgreSQL. |
| Ownership transfer | `backend/scripts/claim_legacy_data.py`, `docs/clerk-ownership-transfer-runbook.md` | Dry-run by default; verifies the account through Clerk; tested. |
| Data copy | `backend/scripts/sqlite_to_postgres.py` | Rehearsed on a copy of your real database. |

How the container start was checked without Docker (the daemon is not running on this machine): I built a
clean environment from exactly the files the Dockerfile copies and the filtered lock, ran
`alembic upgrade head` on an empty PostgreSQL, started uvicorn in production mode, and confirmed `/health`
200, `/docs` 404, `/api/tasks` 401 with the headers above, and that a bad configuration crashes at import with
a clear list. **The image itself has not been built**; Railway's first build is its real test.

## 3. Stage 1 steps (each needs your authorization)
1. **Accounts.** Create the Neon project (region next to Railway and Vercel, e.g. AWS us-east-1) and note the **direct** (non-pooled) connection string. Create the Railway project.
2. **Railway service.** New service from the GitHub repository (the deployment branch), **Root Directory `backend`** (it finds the Dockerfile). Set the variables from `backend/.env.production.example` (Neon URL with `?sslmode=require`; `CLERK_SECRET_KEY` of the dev instance for Stage 1; `CLERK_AUTHORIZED_PARTIES` and `FRONTEND_URL` = the Vercel production URL; empty `CORS_ORIGINS`; a **new** `GOOGLE_TOKEN_ENCRYPTION_KEY`). Health check path `/health`. **Exactly one replica, no autoscaling.** Railway's config-as-code is being deprecated, so these are dashboard settings, not a committed file.
3. **Vercel.** Replace `railway-backend.invalid` in `frontend/vercel.json` with the Railway domain; `npm run build && npm run check:deploy` must print "Deployment configuration looks ready." Remove `CLERK_SECRET_KEY` and the `GOOGLE_*` variables from the Vercel project (unused there). Keep Deployment Protection **on**. Deploy a **preview** first.
4. **Clerk.** Restrict sign-ups to an allowlist (your email). Make sure the Vercel URL is accepted by the dev instance.
5. **Google Cloud.** Add the redirect URI `https://<vercel-url>/api/integrations/google-calendar/callback` and yourself as a test user. Keep the app in Testing.
6. **Smoke test the empty system** (see 4): sign in, add and delete a test task, `/health`, headers.
7. **Backup** the (empty) Neon database and run the **restore drill** once (`docs/backup-and-restore.md`).
8. **Load your data.** Stop the local backend; SQLite online-backup of the local database; `alembic upgrade head` on Neon; `sqlite_to_postgres.py` dry run, then `--execute`; require "Every table matches the source exactly." The local SQLite file is only ever read.
9. **Claim.** Follow `docs/clerk-ownership-transfer-runbook.md` (`--instance test` for Stage 1).
10. **Reconnect Google Calendar** in the deployed app.
11. **Promote** the frontend to production only after 1 to 10 pass, and keep Deployment Protection until you decide to open it.

## 4. Smoke tests after each deployment
- `GET /health` through the Vercel URL returns `{"status":"ok"}`; `/docs` returns 404.
- Signed out: every page redirects to sign-in; `GET /api/tasks` returns 401 with `Cache-Control: no-store`.
- Signed in: add, complete and delete a task; reload; it persisted (so the database is really Neon).
- Response headers contain the security headers from section 2; the browser console shows no
  **Content-Security-Policy-Report-Only** violations for sign-in (if Clerk needs another host, add it, then
  switch the header name to `Content-Security-Policy`).
- Google: Connect, consent, return to the Calendar page; events appear; Disconnect works.
- A second (allowlisted, throw-away) account sees none of your data.

## 5. Rollback and cost control
- **Frontend:** `vercel rollback` or redeploy the previous deployment; nothing else depends on it.
- **Backend:** redeploy the previous Railway deployment. Migrations are additive, so older code still runs.
- **Database:** Neon branch restore (6 hours on Free) or restore a verified backup into a fresh branch.
- **Local:** your SQLite database and local servers are never modified by any step, so the local app remains a complete fallback.
- **Cost:** Railway Hobby $5/month (includes $5 usage; the whole amount is billed if usage exceeds it), Neon Free $0, Vercel Hobby $0. Set a usage limit on Railway.

## 6. Known limits and follow-ups
- One backend instance only (in-memory import previews, request pacer, Google token cache).
- The CSP is report-only until Clerk's hosts are confirmed in a real browser session.
- Vercel proxies `/api` to Railway; very long requests are not expected (cover lookups are small batches), but check the first Goodreads import.
- Not yet built: the `relink` command for Stage 2, and any rate limiting on the API.
