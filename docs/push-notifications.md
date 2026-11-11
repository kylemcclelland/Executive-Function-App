# Rule of Life push notifications

Phase 1: a browser can grant notification permission, create a secure Web Push subscription and
manage it through the authenticated API. Phase 2 (below): a standalone dispatcher delivers
scheduled reminders. **Delivery is off by default everywhere** — it becomes operational only by
deliberately setting `PUSH_DELIVERY_ENABLED=true` in the backend environment. Until then a
subscription only makes a browser *ready*, and the UI says exactly that.

## Architecture

- **Service worker** `frontend/public/sw.js`, served by Vercel from the frontend origin at `/sw.js`
  with scope `/` (static files are served before the SPA rewrite, so it is not rewritten to
  `index.html`; `vercel.json` sends it with `Cache-Control: no-cache` so updates are picked up).
  It only handles `push` (shows a notification named after the prayer, with a dedup `tag`) and
  `notificationclick` (focuses or opens the app at a same-origin path; anything else falls back to
  `/rule-of-life`). No offline caching, no fetch handler, no PWA behaviour.
- **Frontend** `frontend/src/lib/pushNotifications.ts` + the Notifications card in
  `frontend/src/components/ruleOfLife/NotificationSettings.tsx` on the Rule of Life page.
  Permission is requested only from the **Enable notifications** button, never on load; a past
  denial shows instructions instead of re-prompting. The card also disables (unsubscribes) the
  current browser.
- **Backend** `backend/app/api/routes/push.py`, Clerk-authenticated like every other route:
  - `GET /api/push/config` — `{configured, public_key}` (public VAPID key only).
  - `GET /api/push/status` — `{configured, subscription_count, delivery: "pending"}`; never
    returns endpoints, keys or another user's data.
  - `POST /api/push/subscriptions` — registers/refreshes this browser (idempotent per endpoint;
    an endpoint re-registered from another signed-in account moves to that account).
  - `DELETE /api/push/subscriptions` — removes this browser's subscription by endpoint; scoped to
    the caller, so a stranger's endpoint deletes nothing.
  Subscription input is untrusted: HTTPS endpoint URL only (no credentials, ≤ 2000 chars), keys
  base64url (≤ 512 chars).
- **Storage** table `push_subscriptions` (migration `backend/alembic/versions/0014_push_subscriptions.py`,
  additive, after `0013`): id, user_id (FK → users, cascade), endpoint, endpoint_hash (SHA-256,
  globally unique — carries the uniqueness constraint), p256dh, auth, failure_count /
  last_failure_at (for the Phase 2 sender to retire dead subscriptions), timestamps. Multiple
  browsers per user are simply multiple rows. The endpoint and browser keys are public-key
  material useless without the server's VAPID private key, which is **never** stored in the
  database or logs — it lives only in the backend environment. (If at-rest encryption is wanted
  later, the Fernet `TokenCipher` used for Google refresh tokens can wrap `p256dh`/`auth`.)

## Environment variables (backend / Railway)

Generate once per environment with `python backend/scripts/generate_vapid_keys.py` (prints to the
terminal only; commit nothing):

- `VAPID_PUBLIC_KEY` — base64url uncompressed P-256 public key; the only value sent to browsers.
- `VAPID_PRIVATE_KEY` — base64url 32-byte private scalar; secret, backend env only.
- `VAPID_SUBJECT` — `mailto:` contact for push services (used when sending).
- `PUSH_DELIVERY_ENABLED` — master switch for the dispatcher; **defaults to false**.
- `PUSH_REMINDER_EXPIRY_MINUTES` (30), `PUSH_CLAIM_LEASE_SECONDS` (120), `PUSH_MAX_ATTEMPTS` (5)
  — optional dispatcher tuning; the defaults are sensible.

Unset keys are safe: `/api/push/config` reports `configured: false`, subscription attempts
return 503, and the UI shows "not available on this server yet".

## Browser support and local development

Web Push needs a secure context: HTTPS in production (Vercel/Railway already are) or
`http://localhost` in development. Supported in Chrome, Edge, Firefox; Safari ≥ 16.4 — on iOS
only for an installed home-screen app. Unsupported browsers see "Your browser does not support
push notifications." Locally, the Vite dev server serves `public/sw.js` at `/sw.js` and proxies
`/api` as usual; set the VAPID variables in `backend/.env` to exercise subscription.

No CSP change was needed: the report-only policy already allows `worker-src 'self'` and
`connect-src 'self'` (the API is same-origin via the Vercel rewrite). CORS, Clerk auth and the
backend security headers are unchanged.

## Subscription lifecycle

1. User clicks **Enable notifications** → browser permission prompt (`granted`/`denied`/dismissed).
2. On grant: the service worker is registered, `PushManager.subscribe` runs with
   `userVisibleOnly: true` and the public VAPID key, and the resulting endpoint + keys are POSTed.
3. Re-subscribing refreshes the same row (dedup by endpoint hash); signing in as another account
   in the same browser moves the endpoint to that account.
4. **Disable notifications in this browser** unsubscribes locally and DELETEs the registration.
5. Deleting a user cascades away their subscriptions. `failure_count`/`last_failure_at` let
   Phase 2 drop endpoints the push service reports as gone (404/410).

## Phase 2: the scheduled dispatcher

### Architecture

`python -m app.jobs.dispatch_prayer_notifications` — a bounded, repeatable pass designed for a
Railway **scheduled job** (cron), fully independent of the FastAPI process. No browser timers, no
polling, no in-process scheduler, no resident loop: each invocation reads the UTC clock, finds
due occurrences, sends, records outcomes and exits. It reuses the Rule of Life service's own
`occurs_on`/`instant`/`link_for` — there is no second scheduling engine.

Each run, in order:

1. Refuse immediately unless `PUSH_DELIVERY_ENABLED=true` **and** VAPID keys are configured.
2. Mark attempts older than `PUSH_REMINDER_EXPIRY_MINUTES` (default 30) **expired** — a reminder
   is never sent hours late.
3. Seed one durable `push_delivery_attempts` row per (due occurrence × live subscription) for
   every active entry with `notify = true`, skipping occurrences already marked completed or
   skipped and subscriptions the push service has revoked. Seeding uses
   `INSERT … ON CONFLICT DO NOTHING` against the unique `(entry, occurrence_date, subscription)`
   constraint, so overlapping runs collide harmlessly (no SELECT-then-INSERT race).
4. For each claimable attempt: **claim** it with a single atomic `UPDATE … WHERE status='pending'
   AND (claimed_until IS NULL OR claimed_until < now)` setting a bounded lease
   (`PUSH_CLAIM_LEASE_SECONDS`, default 120) and incrementing `attempt_count`. Exactly one worker
   wins; a crashed owner's lease lapses on its own, making the attempt claimable again. The claim
   transaction commits **before** the network request — no transaction is held open during I/O.
   Eligibility is re-checked at send time (entry paused/deleted, occurrence marked, subscription
   revoked ⇒ the attempt is closed unsent).
5. Send via pywebpush with a TTL equal to the expiry window, then record the outcome in a fresh
   transaction.

### Timing guarantees

A reminder fires on the **first invocation after** its UTC instant: accuracy equals the cron
cadence. Recommended: **every 5 minutes** ⇒ at most ~5 minutes late, never early, never
to-the-second. The expiry window (30 min) tolerates a few missed cron slots; beyond it the
attempt is marked `expired`. Web Push is **at-least-once under retries**, not exactly-once: an
ambiguous network failure after a send may cause a duplicate, which the service worker
deduplicates on the device via the notification `tag` (`rule:<entry_id>:<date>`). Acceptance by
the push service (HTTP 201) is **not** proof the device displayed the notification — the status
recorded is "delivered to the push service", nothing stronger.

### Timezones and daylight saving

Occurrence instants come from the existing policy in `services/rule_of_life.py::instant`: the
entry's local time on the occurrence's date in its own IANA zone, converted to UTC. A local time
skipped by spring-forward moves forward with the zone's rules; a repeated fall-back hour resolves
to its **first** occurrence (PEP 495 `fold=0`). Either way one occurrence maps to one UTC
instant, and the unique attempt row makes a second send for a repeated local hour impossible.
Both transitions are covered by tests (`test_push_dispatch.py`).

### Failure classification and retries

- **Permanent** — push service answers 404/410: the attempt is `failed` and the subscription's
  `revoked_at` is set. It is never sent to again (re-subscribing from the browser revives it).
- **Temporary** — 429, 5xx, or a network exception: the attempt stays `pending`; the lease column
  doubles as exponential backoff (`lease × 2^(attempts−1)`), retried on later runs up to
  `PUSH_MAX_ATTEMPTS` (default 5), then `failed`. A retry falling outside the expiry window is
  marked `expired` instead.
- `last_error` stores only a status code or exception class name — never an endpoint, key or
  payload; log redaction stays untouched.

### Inspecting and recovering

Delivery history is the `push_delivery_attempts` table (status, attempt_count, due_at,
last_error). A failed invocation needs no manual recovery: state is durable, leases lapse, and
the next cron run picks up whatever is still inside the window; anything older simply expires.

### Railway deployment (not performed — documented only)

1. Set on the backend service: `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` (secret), `VAPID_SUBJECT`,
   and the usual `DATABASE_URL`/`POSTGRES_PASSWORD` (the dispatcher reads the same
   environment-driven `Settings` as the API — no hardcoded URLs; locally it uses `backend/.env`).
2. Apply migrations `0014` and `0015` (both additive) — **only with explicit approval**; the
   development database is still at `0013` and nothing in this change applies them.
3. Add a Railway cron job running `python -m app.jobs.dispatch_prayer_notifications` every
   5 minutes in the backend image.
4. Flip `PUSH_DELIVERY_ENABLED=true` to go live; unset or `false` makes every invocation exit
   with `{'skipped': …}` without sending. Overlapping or duplicate cron invocations are safe by
   design (atomic claims + unique attempts).

### Payloads and safety

Payloads carry only the prayer's title, `Scheduled for HH:MM`, the dedup tag, and an internal
route built from our own data (`link_for`): an Office hour opens on the occurrence's **own
liturgical date** (`/divine-office?date=…&hour=…`), a devotion opens its Oratory route
(`/devotions/<slug>`). No user notes, tokens, keys or endpoints — and the service worker refuses
any non-same-origin path regardless. Notification destinations are only ever the stored
PushManager subscriptions; no user-supplied URL is accepted anywhere.

### UI states

Browser unsupported · permission required (button-gated prompt) · permission denied
(instructions, no re-prompt) · server unconfigured · **subscribed, delivery pending** ("ready …
not active yet") · **enabled** ("Prayer reminders are enabled for this browser") — shown only
when `/api/push/status` reports `delivery: "active"`, i.e. the server itself has the flag on. A
revoked subscription drops out of `subscription_count`; the browser can simply re-enable.

### Remaining before real-device verification

- Apply `0014`+`0015` to a staging database (with approval) and configure real VAPID keys.
- A manual end-to-end check on a real browser/device: enable, run the dispatcher once near a
  scheduled time, confirm the notification text, tag deduplication and click-through navigation
  (push display cannot be proven server-side).
- iOS Safari requires the app to be installed to the home screen; untested.
