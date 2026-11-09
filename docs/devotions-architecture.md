# Devotions: the prayer page framework and its editorial safeguards

**Status: framework only.** The application can display a prayer or a multi-step devotion and can enforce
the approval workflow. **No prayer or devotional text has been written, seeded, stored or published.** A fresh
database holds zero devotions and zero prayer texts (migration `0010` creates empty tables; a test asserts it).

## The promise, and where it is enforced

> A prayer text reaches a reader only if a named person entered it from a cited source, a named approver
> approved exactly those words, and nothing has changed since.

The application never composes, completes, paraphrases, modernises, reconstructs or translates prayer wording.
There is no code path that generates text and no AI dependency in the devotions code. Software cannot judge
whether wording is faithful, so the safeguards are procedural and structural: every text carries who entered it,
where it came from, who verified the source and who approved it, and text with no attributable source cannot
advance past `proposed`, whoever or whatever wrote it.

Three independent layers hold the line, so no single bug opens it:

| Layer | What it does | Where |
|---|---|---|
| 1. Rules | Roles, order of states, and what each state requires | `app/services/devotions.py`, `app/api/routes/devotions.py` |
| 2. Fingerprint | A SHA-256 of the approved content is stored at approval and **re-checked on every read**. Content changed any other way (manual SQL, a future code path) silently stops being served | `text_is_public`, `devotion_is_public` |
| 3. Database | `CHECK` constraints refuse an approved or published row with no approver/time/fingerprint, and any state past `proposed` for a text without a source, attribution and known licence | migration `0010`, `app/models` |

## Data model

```
devotions            slug, title, subtitle, category, estimated_minutes,
                     overview, background, significance,          commentary (never prayer wording)
                     references[], instructions[], steps[],       structure + guidance (never prayer wording)
                     status, created_by, source_verified_*, approved_*, approved_hash, published_at
prayer_texts         devotion_id, slot, language, position, title, body (exact wording),
                     is_translation, translator, source_title, source_edition, source_url,
                     attribution, license_status, license_notes,
                     status, entered_by, source_verified_*, approved_*, approved_hash
devotion_events      append-only log: actor, action, from/to status, note (field names only, never wording)
devotion_bookmarks   (user_id, devotion_id) and nothing else: no dates, counts, streaks or history
```

* **One structure for simple and complex devotions.** A simple prayer is a devotion with one text and no steps. A
  complex one adds `steps`. The same page renders both.
* **Slots.** A step names its prayer by `text_slot` and contains no wording. The Latin and English of one prayer
  share a slot and are separate rows, so **each language is approved separately** and Latin can be published without
  the English or the reverse.
* **Steps** have a `kind` (`instruction`, `prayer`, `response`), an optional `title`, `instruction`, `section`
  (decade, station, mystery group) and `repeat`. Repetition is shown as text ("Pray this 10 times"); nothing counts.
* **Wording is stored exactly as entered** (never trimmed or normalised) and rendered with `white-space: pre-wrap`
  from the stored characters. Versicle/response lines (`℣ ℟ V. R.`) are styled, not altered.
* Prayer text, instruction and historical commentary are different columns and different components, and look
  different on the page (serif reading face in a framed section; sans-serif with a gold rule; ordinary prose).

## Workflow

```
proposed -> source_verified -> pending_approval -> approved -> published        (devotion)
proposed -> source_verified -> pending_approval -> approved                      (each prayer text)
```

| Move | Who | Needs |
|---|---|---|
| → `source_verified` | editor | Text: source title, attribution, a known licence (not `unverified`), and a translator if it is a translation. Devotion: a cited reference if it has background or significance commentary, and a text for every slot its steps use |
| → `pending_approval` | editor | the same checks again |
| → `approved` | **approver** | the same checks; stores approver, time and content fingerprint |
| `approved` → `published` | **approver** | the devotion's approval still matches its content |
| back to `proposed` (withdraw) | approver (editor may withdraw before approval) | clears verification and approval |
| `published` → `approved` (unpublish) | approver | |

No step can be skipped; a move not in the table is a `409`. **The devotion's inclusion and each text's wording are
approved separately.** A published devotion shows only those texts that are individually approved; the others are
simply absent, and the page shows the unpublished placeholder.

### Any change cancels approval

Editing an approved (or in-review) text's wording **or its citation** (source, edition, translator, attribution,
licence, language, slot) resets it to `proposed` and clears every sign-off, so it must be verified and approved again
and is hidden from readers meanwhile. Editing an approved devotion's content (title, overview, commentary, references,
instructions, steps, address) does the same to the devotion, which unpublishes it. A save that changes nothing leaves
approvals alone. Withdrawn or changed content that is unpublished stays unpublished.

## Authorization

Nothing is inferred from being signed in, and nothing is read from the token beyond the verified Clerk user id.

* Roles come **only from server settings**: `EDITOR_CLERK_USER_IDS` and `APPROVER_CLERK_USER_IDS` (verified Clerk
  user ids, `user_...`). Both are empty by default, so nobody holds a role until the operator sets them.
* No endpoint can grant, change or list roles. Token claims such as `role: admin` are ignored (tested).
* Editors enter, edit, verify and submit. Approvers approve, publish and withdraw. One person may hold both
  (a single-owner deployment). Tests cover an editor failing to approve/publish, an approver failing to edit, and an
  ordinary user failing everything.
* Clerk **development and production instances issue different user ids**. When the Clerk instance changes (see
  `docs/clerk-ownership-transfer-runbook.md`), update these two settings too.

## API

Readers (any signed-in user; they only ever see published devotions and approved texts):

* `GET /api/devotions`, `GET /api/devotions/{slug}`: an unpublished or unknown slug gives the **same** `404`.
  The reader payload has no editorial fields (no approver ids, hashes or licence notes).
* `PUT|DELETE /api/devotions/{slug}/bookmark`: a reader's own favourite, nothing else is recorded.

Editorial (`/api/editorial/devotions...`, `403` without a role): list, create, read, patch, delete (not while
approved), `…/transition`, `…/texts` (create, patch, delete), `…/texts/{id}/transition`, `…/events`. This is an
API, **not an interface**: there is no editorial dashboard and no public approval page.

## Front end

* Routes: `/devotions` (library), `/devotions/:slug` (a devotion), `/devotions/preview/:kind?` (layout preview).
  `preview` is a reserved address, so no devotion can take it.
* `DevotionView` is the single template: Header (back link, title, subtitle, category, duration, optional bookmark),
  Overview (overview, background, significance, sources), How to Pray (numbered instructions, sequence outline;
  hidden when empty), Prayer Text (Latin/English/Both toggle, text size, exact wording, source, edition, translator,
  attribution, rights; an unpublished placeholder when nothing is approved).
* **Prayer mode** is a full-screen, distraction-free reader. With steps it moves with Previous/Next or the arrow
  keys; without steps it is one continuous reading. It sends no requests and stores no activity. Only two display
  preferences (text size, language) are remembered in the browser. There are no counts, streaks, completion messages or
  scores anywhere (tested).
* The layout preview uses clearly labelled placeholder constants in `src/lib/devotionPlaceholders.ts`. They are never
  stored or sent, and contain no real prayer. Citation links render as links only for `http(s)` addresses.
* Accessible by construction: landmark sections with headings, `aria-pressed` toggles, `lang` on every prayer text,
  focus-trapped dialog with Escape, 40 to 46 px touch targets, design-token colours only (light and dark both audited
  for contrast with no findings at 390 px and 1440 px), mobile-first CSS.

## The Oratory (browsing the library)

`/devotions` is **The Oratory**, the landing page for the published library (UI only: no backend change, no content).

* **One request, filtered in the browser.** The page loads `GET /api/devotions` once; search and categories filter that list, so
  typing sends nothing. Search matches every word against the **title, subtitle (the short description) and category**,
  ignoring case, accents and extra spaces. (The list payload carries no overview text, so overview wording is not searched.)
* **Categories** are All Devotions, Daily Prayer, Our Lord, Our Lady, Saints, Liturgical Seasons and Other. A devotion's free-text
  `category` is matched to these case-insensitively; **anything else, or none, appears under Other.** When entering real content,
  use these exact names for the category if you want it under a specific tab.
* **Saved devotions** are the reader's bookmarked published devotions (from the same list). They are not narrowed by search or category.
* Search and category live in the address (`?q=...&category=our-lady`), so Back from a devotion returns to the same view.
* **States are distinct.** An empty library ("No devotions have been added yet..."), a category with nothing in it, a search with no
  matches, and nothing saved each have their own message. **401, 403, 404, server errors (5xx) and network failures are errors**
  with their own wording and are never shown as an empty library; 403 offers no retry.
* No streaks, scores, percentages, reminders or analytics, and browsing stores nothing.

## Tests

* `backend/tests/test_devotions.py`: authorization, workflow, source requirements, per-language approval,
  invalidation after any change, tampering behind the app's back, database refusals, input rules, reader privacy,
  bookmarks, empty-by-default.
* `frontend/src/test/devotions.test.tsx`: simple and complex layouts, missing sections, Latin/English, exact wording,
  prayer mode, the no-tracking guarantees, pages, and the mobile-first stylesheet contract.

## Before real content can be added

1. **Set the roles** (`EDITOR_CLERK_USER_IDS`, `APPROVER_CLERK_USER_IDS`) on Railway. Until then nobody can enter
   anything. Apply migration `0010` (additive; it runs on the next backend deploy, which has not happened).
2. **An editorial interface.** Today content is entered through the role-gated API. Decide whether you want a small
   private editing screen; it must stay behind the same roles.
3. **A source policy.** Decide which editions and translations are acceptable and their licence terms, per text
   (`public_domain`, `licensed`, `permission_granted`). Modern English translations are usually under copyright.
4. **Approve content yourself or with a reviewer you trust.** The software records who approved what; it cannot judge
   whether wording is faithful. Compare each text to its cited source before approving.
5. Optional hardening: require the approver to differ from the editor (off now because this is a single-owner app),
   and add Latin/English paired display checks if you want both versions required together.
6. When real devotions exist, add the first one with `status` flow end to end and check it on staging with
   Deployment Protection still on.
