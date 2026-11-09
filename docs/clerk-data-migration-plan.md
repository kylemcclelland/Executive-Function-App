# Plan: attaching existing Optima Pars data to a Clerk account

**Status: proposal. Nothing in this plan has been run against any real database.**
It needs the owner's decisions (section 5) before any step in section 4 is executed.

## 1. What exists today

Verified by read-only queries against `backend/data/executive_function.db`
(Alembic revision `0007`):

| Table | Rows | Linked to a user by |
|---|---|---|
| `users` | 1 | — (`id = 00000000-0000-0000-0000-000000000001`, timezone `UTC`) |
| `books` | 2,170 | `user_id` |
| `notes` | 5 | `user_id` |
| `tasks` | 4 | `user_id` |
| `projects` | 3 | `user_id` |
| `inbox_items` | 2 | `user_id` |
| `project_notes`, `project_milestones`, `project_updates` | 1 each | `user_id` |
| `work_sessions`, `daily_priorities`, `note_links` | 0 | `user_id` |
| `task_steps` (0), `note_tags` (3) | | no `user_id`; owned through their parent task / note |
| `cover_lookups` (22), `cover_service_state` (2) | | not user data (facts about ISBNs, a rate-limit timer) |

**Every user-owned row belongs to the single pre-authentication user**
(`...0001`). That identity was a hard-coded constant, not an account.

Relationships that must survive (all already use `user_id`/parent foreign keys, none
involve the Clerk id): task → project / milestone, task → steps, inbox item → converted
task, project → milestones / notes / updates, work session → project / task, note →
book / project / tags, note ↔ note links, daily priority → task.

## 2. What has already been done (additive, reversible)

Migration `0008` adds a nullable, unique `users.clerk_user_id`. It changes no row.
The backend maps a verified Clerk `sub` to a user by that column, creating a fresh empty
user the first time a Clerk account is seen. The legacy user's `clerk_user_id` is `NULL`,
so **no Clerk account, including a brand-new one, can reach the legacy data**. It is
simply dormant until claimed. Rehearsed on a copy of the real database: all row counts
and ownership identical after upgrade, `integrity_check` and `foreign_key_check` clean.

The migration has **not** been applied to your live database; run
`alembic upgrade head` from `backend` after taking a backup (see section 5, question 1).

## 3. Proposed claim: link, do not re-key

Set one column on one row:

```sql
UPDATE users SET clerk_user_id = :owner_clerk_id
WHERE id = '00000000-0000-0000-0000-000000000001' AND clerk_user_id IS NULL;
```

No book, note, task, project or relationship row is touched, so nothing can be orphaned
or duplicated, and relationships are preserved by construction. The legacy UUID simply
becomes that account's permanent internal id.

**Complication:** the owner will almost certainly sign in once before the claim, and the
first API call auto-creates an *empty* user for their Clerk id. The unique index then
blocks the `UPDATE`. The claim therefore has to remove or unlink that empty row first,
inside the same transaction, and only after proving it is empty:

```sql
BEGIN;
-- Abort unless the auto-created row owns nothing (repeat for every table with user_id).
SELECT (SELECT COUNT(*) FROM tasks WHERE user_id = :empty_id)
     + (SELECT COUNT(*) FROM books WHERE user_id = :empty_id)
     + ... AS owned_rows;          -- must be 0
DELETE FROM users WHERE id = :empty_id AND clerk_user_id = :owner_clerk_id;
UPDATE users SET clerk_user_id = :owner_clerk_id
 WHERE id = '00000000-0000-0000-0000-000000000001' AND clerk_user_id IS NULL;
-- Expect exactly 1 row updated.
COMMIT;
```

(Alternative that deletes nothing: set the empty row's `clerk_user_id` to `NULL` instead
of deleting it, leaving one harmless dormant user.)

### Alternatives considered and rejected

- **Auto-assign to the first / any new sign-up.** Arbitrary; whoever registers first would
  receive all your data. Rejected, as you specified.
- **Re-key `users.id` to a value derived from the Clerk id.** Rewrites the `user_id` on
  ~2,200 rows across 11 tables and every foreign key to `users`; strictly more risk than
  linking for no benefit.
- **A `CLAIM_LEGACY_DATA=true` environment switch.** Makes ownership depend on a flag and
  a race. Rejected; the claim should be a deliberate one-off with a recorded outcome.

## 4. Procedure (once approved)

1. Stop the backend. Back up using SQLite's online backup (not a plain file copy of a live
   database) and verify the copy with `PRAGMA integrity_check`.
2. `alembic upgrade head`.
3. Sign in once as the owner so the Clerk account exists; read its id (`user_...`) from
   the Clerk dashboard → Users. **Do not copy it from a log or guess it.**
4. **Dry run:** print per-table row counts for the legacy user and for the empty
   auto-created user, and the planned statements. Change nothing.
5. Run the transaction above. Assert: exactly one legacy row updated; total row count in
   every user-owned table unchanged; `PRAGMA foreign_key_check` empty.
6. Sign in as the owner: the app shows the 2,170 books, 5 notes, 4 tasks, 3 projects, etc.
   Sign in as a second throwaway account: it must see nothing.
7. Keep the backup until you are satisfied.

**Rollback:** restore the backup, or `UPDATE users SET clerk_user_id = NULL WHERE id =
'...0001'` (no data moved, so nothing else needs undoing). A deleted empty user is
recreated automatically at the next sign-in.

## 5. Decisions needed from you (nothing proceeds without them)

1. **Which database file is canonical?** `.env` points `DATABASE_URL` at
   `C:/Users/uvaga/Executive-Function-App/backend/data/executive_function.db`, while the
   repository you are working in has its own `backend/data/executive_function.db`. Both
   currently hold identical content (same schema revision and row counts, same timestamps),
   but they are separate files and will diverge. Pick one and retire the other.
2. **Which Clerk account is the owner?** The exact `user_...` id (section 4, step 3).
3. **May the claim delete the auto-created empty user row** (verified empty first), or
   would you rather it be unlinked and left in place?
4. **Timezone:** the legacy user is `UTC`. If you changed your timezone in Preferences
   after signing in, which value should win after the claim?
5. **Backups:** the `backend/data/*.pre-*.db` files are an informal backup trail. Do you
   want a standing backup step before every migration going forward?

## 6. Not in scope / follow-ups

- Postgres: identical procedure (`BEGIN … COMMIT`, same SQL); only the backup command
  differs (`pg_dump`).
- A reusable `claim_legacy_data` script with the dry-run and assertions above can be
  written once you approve this plan.
- There are no composite same-owner foreign keys (e.g. a task's `project_id` is not
  forced to belong to the same user); ownership is enforced in application code, which a
  route-by-route audit found consistent. Database-level enforcement is a worthwhile
  hardening before more than one real user exists.
