# Devotions: the prayer page framework and its editorial safeguards

> **Simplified (current state).** The approval and publication workflow described below has been retired. The Oratory shows every devotion and
> every prayer text held; there is no editorial dashboard, no editor or approver role (`EDITOR_CLERK_USER_IDS` / `APPROVER_CLERK_USER_IDS` are
> no longer read) and the editorial API endpoints are removed. The reader API is `GET /api/devotions`, `GET /api/devotions/{slug}` and the
> bookmark routes, all for a signed-in user. A text with no wording is a citation-only record and is labelled "Citation only". The database
> columns and the historical event log are kept unchanged (nothing was dropped); the sections below describe that history and how the data was
> imported, and remain accurate about provenance, seeding and the exact-wording rule.


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

## Editorial review (phase 2)

The private review interface lives at `/editorial/devotions` (queue), `/editorial/devotions/:id` (review) and
`/editorial/devotions/:id/preview` (private preview). It reuses the existing API and components; nothing parallel exists.

* **Access.** Every screen asks `GET /api/editorial-access`. A signed-in person with no role sees a plain "Editorial review is
  private" page and the queue is never requested. The server enforces roles on every request regardless, so hiding a screen is
  kindness, not security. The Oratory shows an "Editorial review" link to editors and approvers only.
* **The queue** shows, per devotion: title, category, workflow status, **English and Latin status separately**, source
  verification, reproduction rights, last updated, and a Review action; filterable by status and category (kept in the address).
  It is a table on wide screens and stacked cards on phones.
* **The review screen** shows the devotion's information (prose labelled **Unapproved editorial prose** while it is AI-drafted and
  the devotion is not yet approved), its structure, and each prayer text with its exact wording, source, issuing authority,
  edition, publication date, link, translation attribution, rights and the basis for them, when it was copied, who entered,
  verified and approved it, and the last decision with its reason. A **Language** dropdown (the same component as the public
  pages) chooses which language you are looking at; **it never changes a status**. "Compare languages side by side" shows both
  at once, read-only.
* **Decisions** (each behind a confirmation dialog; any that turns something down needs a reason, recorded in the log):
  mark source verified, submit for approval, approve (names the exact language and warns that any later change cancels it),
  **return for further research**, **reject** a proposed text, **reject approval**, **withdraw** approval, publish (lists which
  languages readers would see), unpublish. Buttons that the signed-in role cannot use are disabled with the reason shown.
* **Rights gate.** A text can be verified only if it holds wording, names its source and attribution, and its rights are
  `public_domain`, `licensed` or `permission_granted`. `restricted` (the owner's terms do not clearly allow republishing) and
  `unverified` block it, in the service **and** by database constraint.
* **Withheld wording.** A text may be *only a citation*: empty wording, a source link and the reason. This is allowed only while it
  is `proposed` (migration `0011` relaxes that one constraint and keeps it strict for every later state). The review screen
  explains why there is no wording and links to the source.
* **Independent languages.** English and Latin are separate records with separate sources, approvals and rejections. A devotion
  can be published with English alone; Latin appears only after its own approval (tested).
* **Publication prerequisites.** Publishing needs the devotion approved, at least one prayer text a reader could see, and an
  approved text for every non-optional prayer step (own or reused). The review screen lists each unmet condition once.
* **Preview.** `GET /api/editorial/devotions/:id/preview` returns the devotion as the Oratory would render it, **including
  unapproved texts, each marked** with its status and whether a reader would see it. It is role-gated, never public, and
  the front end reuses `DevotionView` with an "Unpublished preview" banner.

### Reusing prayers, choices and optional customs

* A step may name `devotion_slug` + `text_slot`: the prayer is **kept once, in its own devotion, and reused** (the Rosary uses the
  Sign of the Cross, Creed, Our Father, Hail Mary and Glory Be). A reused prayer reaches a reader only if its own devotion is
  published and the text approved; a devotion cannot be published before the devotions it reuses.
* `group` marks steps the reader **chooses between** (the four sets of mysteries), `choice_label` names the choice ("Mysteries"),
  and `optional` marks a traditional custom (Fátima prayer, three Hail Marys) that never blocks publication.
* Prayer mode keeps the reader's place when the language changes, and keeps the chosen set and decade. There are no checkboxes,
  counts or completion messages.

### The Language dropdown

One registry (`SUPPORTED_LANGUAGES` in `lib/devotions.ts`: English, Latin) drives the dropdown, the messages and the editorial
screens, so another language is one more entry plus texts. English is the default and the choice is remembered. A language with no
text for a prayer shows "**Latin text is not yet available for this devotion**" (or "...this prayer") with buttons to read in a
language that exists. **Another language is never shown in its place and nothing is ever translated automatically.**

### Seeding the ten drafts

`backend/scripts/seed_devotion_drafts.py` creates the ten foundational devotions as `proposed` drafts
(Sign of the Cross, Our Father, Hail Mary, Glory Be, Apostles' Creed, The Angelus, The Holy Rosary, Examination of Conscience,
Act of Contrition, Prayer to St. Michael) plus their sourced text records. It is **idempotent**: an existing devotion is left
completely untouched (status, approvals, text, edits), repeated runs duplicate nothing, and `--add-missing-texts` only adds a
source text that is absent. It defaults to a dry run, refuses a database not at migration `0011`, and refuses a SQLite database
that holds user data. It never approves or publishes anything. The explanatory prose is AI-drafted and marked `ai_draft`; **all
prayer wording comes from `seed_data/prayer_sources.json`**, copied programmatically from cited sources (see
`docs/devotion-source-research.md`) and stored with the hash of what was copied, so a reviewer can check it.

## The Prayers of the Rosary (a supplied document)

The owner supplied a document, *The Prayers of the Rosary* (English and Latin; `The Prayers of the Rosary.txt`, SHA-256 `9bf41f32…7c74`, identical
in wording to the PDF `Prayers_of_the_Rosary_English_and_Latin.pdf`). It names no author, edition, translator or rights holder, so its texts are recorded
as **"User-supplied document"**, rights **unverified**, and sit in the normal review queue (`proposed`: nothing is verified, approved or published).

* `backend/scripts/import_rosary_prayers.py` slices the document by its headings into `seed_data/rosary_document.json` (never touches a
  database, writes no wording). Only the page-number lines are dropped and the PDF's page-width line wraps are joined with one space; versicles and
  responses (`V.`/`R.`) keep their own lines. It stops rather than guess. The document's own introductions and the Fatima "Note" are kept
  as source commentary in each text's notes, apart from the wording. The pronunciation section is not a prayer and is not imported.
* `seed_devotion_drafts.py` stores the ten prayers on **The Holy Rosary** as 20 texts in slots `collection-<prayer>` (English and Latin, in the
  document's order). Wording another devotion already holds (the Baltimore English, the supplied Latin) is a different edition: it is **never overwritten**,
  no second devotion is created for any of the ten prayers, and each text says when another edition exists. Run with `--add-missing-texts` to add
  them to a database where the Rosary already exists; seeding again duplicates nothing.
* The page shows them as an ordered, numbered collection under **The Prayers of the Rosary** with a jump list, the Language dropdown, and an
  optional **Side by side** layout (Latin and English columns, stacked on a narrow screen). A language a prayer lacks is stated, never replaced.
  Only approved wording reaches the page, so it is absent until a reviewer approves each text.

## Wording typed by the owner

`backend/scripts/seed_data/owner_supplied_texts.json` holds wording the owner typed in a message (currently the English Act of Contrition),
stored exactly as given, with source "User-supplied text", rights `unverified`, status `proposed`. Where it says it replaces an earlier cited
edition, seeding creates only the owner's text for that slot, and the earlier record stays in `prayer_sources.json`. For a database seeded before,
`seed_devotion_drafts.py --apply-owner-supplied` replaces a text only if it is still exactly the earlier edition (through the normal edit path:
approvals are discarded and only field names are logged); a text edited since is never touched. Tests: `backend/tests/test_owner_supplied_text.py`.

## Tests

* `backend/tests/test_devotions.py`: authorization, workflow, source requirements, per-language approval,
  invalidation after any change, tampering behind the app's back, database refusals, input rules, reader privacy,
  bookmarks, empty-by-default.
* `backend/tests/test_devotion_review.py`: withheld wording and rights gates, source metadata as approved content, independent
  English and Latin, publication prerequisites, reused prayers, grouped and optional steps, recorded decisions, the private
  preview, and who may reach which endpoint.
* `backend/tests/test_seed_devotion_drafts.py`: the ten drafts, idempotency, never overwriting, no invented wording (including a
  check that every stored wording still matches the hash recorded when it was copied), the Rosary's structure, refusals.
* `backend/tests/test_rosary_document.py`: the document's import word for word, refusals, provenance, no overwriting or duplicates, the review
  queue, and no public exposure of unapproved wording. `frontend/src/test/rosary.test.tsx`: the ordered collection, language switching, side by side.
* `frontend/src/test/devotions.test.tsx`, `oratory.test.tsx`, `language.test.tsx`, `editorial.test.tsx`: layouts, the library,
  the Language dropdown (default, switching, persistence, missing language, no substitution, guided position), the editorial
  queue, review, role-aware actions with confirmation dialogs, the preview, error handling for 401/403/404/5xx/network, and the
  mobile-first, token-only stylesheets.

## Before devotions can be published

1. **Apply migration `0011`** (and `0010` if not yet applied) to the target database: additive apart from two relaxed or
   tightened constraints (see its docstring). It runs on the backend's next deploy; a backup first is recommended.
2. **Seed the drafts** with `scripts/seed_devotion_drafts.py` (dry run first).
3. **Set the roles** (`EDITOR_CLERK_USER_IDS`, `APPROVER_CLERK_USER_IDS`) on Railway. Until then nobody can enter or approve
   anything, including you. Use the Clerk user ID of the instance in use (development and production IDs differ).
4. **Resolve the open source questions** in `docs/devotion-source-research.md` (the Latin texts and the examination of conscience
   need either written permission or a cleared source). Until then those texts stay as citations.
5. **Review every text yourself against its source.** The software records who approved what and ties approval to the exact
   wording and source details; it cannot judge whether wording is faithful or whether an older English form is the one you want.
6. Optional hardening: require the approver to differ from the editor (off now because this is a single-owner app), and an
   editing screen for wording and metadata (today those are changed through the role-gated API).
