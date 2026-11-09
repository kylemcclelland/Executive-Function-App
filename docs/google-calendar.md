
# Google Calendar integration

Optional, read-only, per-user. Any signed-in Optima Pars user can connect **their own** Google
account; nothing is tied to the developer's account, and Optima Pars is fully usable without it.

## How it works

1. A user signs in with Clerk. The Calendar page asks the backend for `GET /api/integrations/google-calendar/status`.
2. If not connected it shows **Connect Google Calendar**. Nothing is sent to Google until the user
   presses it.
3. `POST …/connect` (Clerk-authenticated) creates a random single-use `state` bound to that user
   (stored only as a SHA-256 hash, expires in 10 minutes) and a PKCE verifier (stored encrypted),
   and returns Google's consent URL (`access_type=offline`, `prompt=consent`, scope
   `calendar.readonly`, plus `openid email` to show which account is connected).
4. Google redirects the browser to `GET …/callback`. That request carries no Clerk token, so it is
   authenticated **only** by the state: it must exist, be unexpired and unused, and is consumed
   atomically (a replay or a guess is rejected before Google is contacted). The user it belongs to
   is the user who started the flow, never anything in the request.
5. The backend exchanges the code (with the PKCE verifier), checks the calendar scope was actually
   granted, and stores the **refresh token encrypted** (Fernet). Access tokens are never stored;
   they are kept briefly in process memory and refreshed on demand.
6. `GET …/events` uses the signed-in user's own refresh token. `DELETE …/disconnect` revokes the
   token at Google (best effort) and erases it locally.

Refresh tokens: Google does not return one on every authorization. If a reconnect returns none,
Optima Pars keeps the stored token for the *same Google account*; otherwise it asks the user to try
again. If Google later rejects a refresh token (revoked, expired, password change), the connection
becomes `needs_reauth` and the UI offers **Reconnect**.

### API

| Endpoint | Auth | Notes |
|---|---|---|
| `GET /api/integrations/google-calendar/status` | Clerk | `configured`, `status` (`not_connected`/`active`/`needs_reauth`), account email, last sync |
| `POST …/connect` | Clerk | returns `{authorization_url}` |
| `GET …/callback` | `state` only | redirects to `FRONTEND_URL/calendar?google=<outcome>` |
| `GET …/events` | Clerk | `time_min`, `time_max` (RFC 3339 with zone, default now → +30 days, max 366 days), `page_size` (1–100), `page_token` |
| `DELETE …/disconnect` | Clerk | idempotent, 204 |

Events come from the primary calendar with recurring series expanded into occurrences. Timed
events are UTC instants plus their IANA zone; all-day events are dates with an inclusive last day;
cancelled events are dropped. Only title, time, location and link are requested; descriptions,
attendees and conference details are not.

### Data stored

`google_calendar_connections` (one row per user in v1: status, scopes, encrypted refresh token,
Google account id/email, timestamps) and `google_oauth_states` (pending attempts). **No calendar
events are stored.** A partial unique index allows one live connection per user; supporting several
Google accounts later means replacing it with `UNIQUE (user_id, google_account_identifier)`.
Migration `0009` is additive.

## Server configuration

Add to the repository-root `.env` (never commit it):

```
GOOGLE_CLIENT_ID=<from Google Cloud>
GOOGLE_CLIENT_SECRET=<from Google Cloud>
GOOGLE_TOKEN_ENCRYPTION_KEY=<see below>
# Must exactly match an Authorized redirect URI on the OAuth client:
GOOGLE_REDIRECT_URI=http://localhost:5173/api/integrations/google-calendar/callback
FRONTEND_URL=http://localhost:5173
```

Generate the encryption key once and keep it safe:

```
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Losing this key means every user must reconnect** (their stored tokens become unreadable; the
app handles that gracefully). To rotate, put the new key first and keep the old after a comma
(`new,old`); old tokens still decrypt and new ones use the new key.

If any of the three required values is missing the integration is simply not offered, and the
Calendar page says so. The browser never sees the client secret, a refresh token, an
authorization code or an access token. OAuth parameters and tokens are redacted from logs.

## Google Cloud setup

Google renames console sections from time to time (the OAuth screens now live under
**Google Auth Platform**: Branding, Audience, Data Access, Clients, Verification Center). Check
Google's current documentation if a label, limit or requirement below has changed; this section
is guidance, not a substitute for it.

1. **Project and API.** Create a Google Cloud project and enable the **Google Calendar API**.
2. **Branding (consent screen).** App name ("Optima Pars"), user-support email, logo, application home
   page, **privacy policy link**, terms (optional), and **authorized domains** (the domain that
   hosts those pages). Production requires these on a domain you control.
3. **Audience.** Choose **External** so that people outside your own Google Workspace can connect.
   (Internal would restrict it to one Workspace organisation.)
4. **Data access (scopes).** Add `openid`, `.../auth/userinfo.email` and
   `https://www.googleapis.com/auth/calendar.readonly`. Do not add broader Calendar scopes.
   `calendar.readonly` is a **sensitive** scope, which is what triggers verification below.
5. **OAuth client.** Create a client of type **Web application**. Add the exact
   **Authorized redirect URI(s)**: `http://localhost:5173/api/integrations/google-calendar/callback`
   for development (Google permits `http://localhost`), and your HTTPS callback URL for
   production. No JavaScript origins are needed: the code flow runs on the server. Copy the client
   ID and secret into `.env`.
6. **Test users.** While the app is in **Testing**, add each Google account that should be able to
   connect (up to 100). Everyone else is refused by Google.

### Publishing status, and who can actually connect

| Status | Who can connect | Notes |
|---|---|---|
| **Testing** | Only listed test users | Warning screen "Google hasn't verified this app". **Refresh tokens expire after 7 days** for External apps in Testing that request scopes beyond basic profile, so Optima Pars will show *Reconnect* about weekly. Expected, not a bug. |
| **In production, unverified** | Any Google user, but capped (100 new users) and shown a scary unverified-app warning | Not suitable for general release. |
| **In production, verified** | Any Google user | Requires passing Google's verification (below). |

**Optima Pars must not be described as available to all Google users until the project is In
production and verified.** Until then it is limited to the listed test users.

### Verification (required for a sensitive scope in production)

Google reviews the app before removing the user cap and warning. Expect to provide:

- A verified **home page** and **privacy policy** on a domain you own (verify domain ownership in
  Google Search Console and list it under authorized domains); the privacy policy must be
  reachable without signing in and linked from the home page and the consent screen.
- Accurate branding (name, logo) that matches the app.
- A written **justification** for `calendar.readonly` and a **demo video** showing the OAuth
  consent flow and how the data is used in the app.
- Compliance with the **Google API Services User Data Policy**, including the **Limited Use**
  requirements: use Calendar data only to show the user their own events; no selling, advertising
  or human reading except as permitted.

### Privacy policy must say

What is accessed (the signed-in user's calendar event titles, times, locations and links), why
(to display them inside Optima Pars), what is stored (an encrypted refresh token and the connected
Google account's id and email; **no event content**), that tokens are encrypted at rest and never
shared, how to revoke (Optima Pars's **Disconnect**, or <https://myaccount.google.com/permissions>),
how long data is kept (removed immediately on disconnect), a contact address for deletion
requests, and a statement that Optima Pars's use and transfer of information from Google APIs adheres
to the Google API Services User Data Policy, including the Limited Use requirements.

## Testing locally

1. Fill in `.env` as above, add your Google account as a **test user**, restart the backend
   (port 8001) and apply migration `0009` (`alembic upgrade head`, after a backup).
2. Open `http://localhost:5173/calendar`, press **Connect Google Calendar**, accept the warning
   screen, grant calendar access, and you return to the Calendar page.
3. Sign in as a second Clerk user with a different Google test user: each sees only their own events.

## Known limits (version 1)

One Google account and the primary calendar per Optima Pars user; read-only; no push notifications or
background sync (events are fetched when the page is opened and Today refreshes every 5 minutes);
the access-token cache is per server process.
