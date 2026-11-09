# Transferring ownership of the existing data to your Clerk account

Everything created before sign-in existed (your 2,170 books, notes, tasks, projects, inbox) belongs to one
internal "legacy" user, `00000000-0000-0000-0000-000000000001`, which has no Clerk account linked. Until you
deliberately link it, **no one can see that data, including you, and including anyone who signs up.**
Linking is a single, reversible column change; no data row is moved, copied or deleted.

This runbook is how we make sure the link goes to the right person. It is performed with
`backend/scripts/claim_legacy_data.py` (tested: `backend/tests/test_claim_legacy_data.py`). **Nothing here
has been run against any real database.**

## The risk it removes
Whoever's Clerk account gets linked becomes the permanent owner of all the data. The mistakes to prevent are:
linking someone else's account (someone signed up first), linking an account from the wrong Clerk instance
(a development id will never match a production sign-in), linking a throw-away or unverified email, linking
twice, and linking without a recoverable backup.

## Before anything: lock the door
1. In the Clerk dashboard (the instance the deployed app uses), **restrict sign-ups** to an allowlist or
   invitation-only, containing only your email. Do this *before* the deployed app can be reached by anyone else.
2. Keep Vercel Deployment Protection on until the claim is done.
3. Confirm the Clerk **Users** list shows only you (or only accounts you recognize).

## How we verify the correct account
We do not trust a copied id. Four independent checks must agree, and the tool enforces them:

| Check | Where it comes from | What it catches |
|---|---|---|
| The `user_...` id | Clerk Dashboard > Users > your user (copy it there, not from a log or URL) | typos, someone else's id |
| The account's **email and its verified status** | The tool asks **Clerk's API** (with the instance's secret key) and compares Clerk's primary email to `--expect-email`; the address must be *verified* | claiming an account registered with an unverified or different address |
| The **instance** | `--instance live\|test` must match the secret key's prefix (`sk_live_` / `sk_test_`) | claiming with a development account when production was intended (or the reverse) |
| **You**, signing in | You sign in to the deployed app with that account before the claim, and compare the name/email printed by `inspect` with yourself | everything the machine cannot know: "is this really me?" |

Then the tool refuses to proceed unless the database agrees as well: the legacy user is still unlinked, the
new account owns nothing, and a **verified backup under an hour old** exists with the database unchanged since.

## Procedure (each step waits for your go-ahead)
Run from `backend/`. Set secrets in the environment, never on the command line:
`DATABASE_URL` (production, Neon direct connection) and `CLERK_SECRET_KEY` (the same instance the app uses).

1. **Sign in once** to the deployed app with your account. This creates an *empty* account row for your Clerk id.
2. **Inspect (read-only):**
   `python scripts/claim_legacy_data.py inspect --clerk-user-id user_XXXX`
   It prints what Clerk says (name, verified email, created, last sign-in) and what the database holds
   (legacy user unlinked and what it owns; whether your account row exists and that it owns nothing).
   **Stop if the name or email is not you.**
3. **Back up and verify:**
   `python scripts/backup_postgres.py backup --out ~/optima-pars-backups` (see `docs/backup-and-restore.md`).
4. **Dry run** (writes nothing; runs every check):
   `python scripts/claim_legacy_data.py claim --clerk-user-id user_XXXX --expect-email you@example.com --instance live --backup <file> --timezone account`
   `--timezone` is required when your new account already has settings: `legacy` keeps the legacy user's
   timezone (UTC today), `account` keeps the one you chose after signing in.
   By default the empty account row created at sign-in is **removed**; add `--unlink-empty` to keep it as a harmless unlinked row instead.
5. **Execute:** the same command plus `--execute --confirm-clerk-id user_XXXX` (the id typed a second time).
   It re-runs every check inside the transaction that writes, with both rows locked, links the legacy user to
   your Clerk id, removes the empty row, and **rolls back everything** unless exactly one user was linked and
   every other table still has exactly the same number of rows.
6. **Verify as you:** reload the app. Your library, notes, tasks and projects must all be there. Then sign in
   with a second, throw-away account (temporarily allowlisted) and confirm it sees **nothing**.

## Undo
Nothing was moved, so undoing is one statement (the next sign-in recreates your empty account row):

```sql
UPDATE users SET clerk_user_id = NULL WHERE id = '00000000-0000-0000-0000-000000000001';
```

For anything worse, restore the backup into a fresh database (`docs/backup-and-restore.md`).

## Two stages: staging now, production later
- **Stage 1: staging on the Vercel URL with the Clerk *development* instance** (`pk_test_`/`sk_test_`, `--instance test`).
  This is the supported interim setup (see "Domains" in `docs/deployment-runbook.md`). Your development
  account is the one you use today.
- **Stage 2: production Clerk instance on your own domain** (`--instance live`). Clerk states that user data
  cannot be transferred between instances, so your production account has a **different** `user_...` id.
  The design makes the move a one-column change: sign in to production (creating an empty row), take a
  verified backup, then in one transaction delete that empty row and
  `UPDATE users SET clerk_user_id = '<production id>' WHERE clerk_user_id = '<staging id>'`, asserting that
  exactly one row changed and no table's row count changed, after repeating the Clerk-API email/instance
  checks above for the new id. A `relink` command that automates exactly this will be added and tested
  before Stage 2; it is deliberately not built yet.

## What each protection is for (and where it is tested)
| Protection | Test |
|---|---|
| Dry run by default; nothing written without `--execute` | `test_a_dry_run_checks_everything_and_writes_nothing` |
| Wrong email, unverified email, wrong instance, unknown id | `test_it_refuses_unless_everything_checks_out[...]` |
| Legacy already linked; new account already owns data | same |
| No/stale/corrupt backup, or database changed since the backup | same |
| Id must be typed twice; secret key and database required | `test_execute_needs_the_clerk_id_typed_twice`, `test_missing_secret_key_or_database_is_refused` |
| Only the legacy user is linked; row counts unchanged; owner sees data, strangers see none | `test_the_claim_links_the_legacy_data_and_removes_only_the_empty_account` |
| Failure part-way rolls everything back | `test_a_failure_part_way_rolls_everything_back` |
| Real backup, real PostgreSQL | `test_end_to_end_with_a_real_backup` |
