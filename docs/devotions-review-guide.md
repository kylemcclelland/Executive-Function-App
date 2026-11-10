# Reviewing the ten devotions in staging

Nothing in this guide has been run against staging. Each numbered step that changes staging needs your explicit go-ahead.

## 0. What you will see
Ten **unpublished** drafts in a private review queue. Nothing is approved and nothing is public. Twelve prayer texts hold sourced
wording; eight are citations with the wording withheld. See `docs/devotion-source-research.md`.

## 1. Back up, then migrate (needs your authorization)
1. Take and verify a Neon backup: `python scripts/backup_postgres.py backup --out ~/optima-pars-backups`, then `verify` the file
   (the tool now copes with a database one migration behind the code).
2. Deploy the backend with `railway up --service api` from `backend/`. Its start-up runs `alembic upgrade head`, applying `0010`
   (devotions, additive) and `0011` (source metadata; two constraints relaxed or tightened). Neither changes an existing row.

## 2. Seed the drafts (needs your authorization)
```
export DATABASE_URL='postgresql+psycopg://...?sslmode=require'     # via your usual secure route, never on the command line
python scripts/seed_devotion_drafts.py                              # dry run: shows exactly what it would create
python scripts/seed_devotion_drafts.py --execute                    # create the drafts
```
Running it again changes nothing. It never overwrites an existing devotion or any decision you have made.

## 3. Give yourself a role (needs your authorization)
Nobody has an editorial role by default, including you. On Railway set `EDITOR_CLERK_USER_IDS` and `APPROVER_CLERK_USER_IDS` to your
Clerk user ID (a single person may hold both; on the development instance yours is the `user_...` ID shown in Clerk). Redeploy or
restart so the settings load. **Do not add anyone else's ID unless you want them to approve prayers.**

## 4. Review
1. Open **The Oratory** and follow the **Editorial review** link (shown only to editors and approvers), or go to `/editorial/devotions`.
2. Filter the queue by status or category. English and Latin are shown separately.
3. Open a devotion. Use the **Language** dropdown to see English or Latin, or **Compare languages side by side**.
4. For each text, compare the wording with its **source link** and check the edition, translation attribution and rights (open
   **Basis and evidence** for the reasoning and the hashes). Then, in order: **Mark source as verified**, **Submit for approval**,
   **Approve this text**. Each asks you to confirm. Use **Return for further research** or **Reject** (with a reason) if anything is wrong.
5. Use **Preview as readers will see it** to see the page as The Oratory will show it, with unapproved texts marked.
6. Approve the **devotion itself** (separate from its texts), then **Publish**. The dialog tells you which languages readers will see.
   Publish the five simple prayers before **The Holy Rosary**, which reuses them.
7. Publishing is reversible: **Unpublish** or **Withdraw approval** at any time.

## What cannot be approved yet
Citation-only texts cannot be verified (they hold no wording and their rights are not cleared); the review screen says so. Their
sources need permission or a cleared alternative first.
