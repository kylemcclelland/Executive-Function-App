# The Divine Office in The Oratory

**Status (phase 2):** all eight canonical hours (Matins, Lauds, Prime, Terce, Sext, None, Vespers, Compline) are implemented end to end (Roman
Breviary, Rubrics of 1960, universal Roman calendar, Latin and English). Nothing in this module composes liturgical text: every word comes from
the upstream Divinum Officium engine.

Hour commands, verified in upstream's own `web/www/horas/horas.dialog` (`[horas]`: `Matutinum,Laudes,Prima,Tertia,Sexta,Nona,Vesperae,Completorium`):
`prayMatutinum`, `prayLaudes`, `prayPrima`, `prayTertia`, `praySexta`, `prayNona`, `prayVesperae` (note: *Vesperae*), `prayCompletorium`. A test reads that
file and asserts the registry matches it.

## Source and version

* Upstream: <https://github.com/DivinumOfficium/divinum-officium> (Perl; MIT licence).
* **Commit used: `e3e0894e00318a6fc5daae309c845ec5f300837a`** (2026-11-10, "Typo"), a shallow clone kept outside this repository at
  `C:\Users\uvaga\divinum-officium` (about 40,000 files; it is not vendored here). The running API reports the checkout's commit in every response.
* Version string passed to the engine: **`Rubrics 1960 - 1960`** (kalendar `1960`: the 1960 rubrics with the universal Roman calendar).
  The engine also has `Rubrics 1960 - 2020 USA` / `1960 Newcalendar` (kalendar `NC`); they are never used. A test asserts the request names the 1960 version.
  I did not find a date where the two variants' Compline *titles* differ in a quick scan of eleven dates, so the 1960 choice is guaranteed by the explicit
  version parameter, not by a data check.

## How the Office is calculated, and how it is reused

Divinum Officium computes the Office in Perl (`web/cgi-bin/horas/officium.pl` with `horascommon.pl`, `specials*.pl` and the `DivinumOfficium::*`
modules); texts are plain files under `web/www/horas/<Language>/` and the calendar tables under `web/www/Tabulae/`. The calendar logic (precedence
of occurring feasts, concurrence, transfers, the Psalter by weekday, season) lives in that code; **it is reused, not rewritten.**

`backend/app/divine_office/`:

* `run_engine.pl` is a small wrapper (ours): it runs upstream's unmodified `officium.pl` in-process for one request, in the engine's own command-line
  mode (no web server, no network), and appends the engine's computed day data (`@dayname`, winner, rank) as a trailing comment.
* `engine.py` runs it with a fixed argument list (no shell), a 40 s timeout and a minimal environment. If the checkout, Perl or the engine is missing or
  fails, it raises `EngineUnavailable` and the API answers **503 with the reason**. Nothing is substituted.
* `parser.py` cuts the engine's Latin/English table into sections, rows and labelled lines (versicle, response, antiphon, psalm heading, psalm verse
  number, benediction, rubric). It only copies text. A row without a Latin and an English cell is refused, not guessed.
* `service.py` builds the response: date, liturgical day, rank, season, hour, ordered sections, source metadata. In-memory cache of 64 results.
* `GET /api/divine-office/{date}/{hour}?language=both|latin|english` and `GET /api/divine-office/hours`; signed-in users only. `compline` works; the other
  an unknown hour is 404. Each row also carries `aligned` (the engine gave the same number of Latin and English lines) and `marks`: navigable points found
  from the engine's own rubric lines (`Nocturnus I/II/III` or `Ad Nocturnum`, `Te Deum`, `Commemoratio ...`), with the English counterpart taken from the
  same line position when the row is aligned. Marks only index text that is already there; they add and remove nothing.
* An empty or malformed engine answer (no rows, no Latin/English pair) is an error: 503 "The Divine Office is unavailable", never an empty Office.

Not scraped: the public website is never contacted. Not used: any undocumented HTTP endpoint.

### Running it locally

1. A checkout of the upstream repository, and a Perl with `CGI`, `Date::Calc`, `Algorithm::Diff`, `URL::Encode`, `Carp::Clan` (upstream's `cpanfile`).
2. Set in the root `.env` (local only): `DIVINUM_OFFICIUM_PATH`, `DIVINUM_OFFICIUM_PERL` (default `perl`), `DIVINUM_OFFICIUM_PERL5LIB` (optional).
   Unset means the Office reports itself unavailable.
3. This machine's setup: Git for Windows' Perl 5.36 (MSYS). It had no `CGI`/`Date::Calc`, so the pure-Perl modules were unpacked from CPAN into
   `C:\Users\uvaga\divinum-officium-perl5lib`, and `Date/Calc.pm` there is a **local shim** that exposes the pure-Perl `Date::Calc::PP` under the name upstream
   imports (the compiled `Date::Calc` could not be built). The shim is a local tooling convenience, not part of this repository. A native Perl with the
   upstream dependencies would not need it.

## What was verified (against the engine itself)

`backend/tests/test_divine_office.py` (the engine tests skip when no checkout exists). Dates used for **every one of the eight hours**: ordinary weekday
(10 Nov 2026, St Andrew Avellino, III class), Sunday (8 Nov), the Assumption (15 Aug, I class), Christmas, a Lenten weekday with commemorations (4 Mar),
a Lenten Sunday (8 Mar), Easter Wednesday (8 Apr), the Vigil of the Ascension (13 May) and the Ascension (14 May); Good Friday and Holy Saturday (3 and
4 Apr) for completeness only.

* **Sequence:** for each hour and date, the parts are a subset of that hour's known parts, in upstream's order, none repeated, and every part that hour
  always has is present (for example Matins: Incipit, Invitatorium, Psalmi cum lectionibus, Oratio, Conclusio; Lauds and Vespers: a chapter-and-hymn, or the
  Easter-octave verse in its place; Prime: Martyrologium, De Officio Capituli, Lectio brevis). Where upstream omits parts (the hymn and chapter in the Easter
  octave) that is reported, not "fixed".
* **Matins structure:** Christmas, the Assumption (and All Saints, St Peter and Paul in a manual scan) have `Nocturnus I`, `II`, `III`, nine lessons, nine
  psalms and the Te Deum; an ordinary Sunday and a Lenten weekday have one `Ad Nocturnum` with three lessons, and no Te Deum in Lent. The nocturns sit inside the
  engine's single section "Psalmi cum lectionibus"; they are reached through `marks` and the contents, not by splitting text.
* **Commemorations:** Lauds on 4 Mar has two (`Commemoratio S. Casimiri`, `Commemoratio S. Lucii`), on 6, 7 and 9 Mar one each; they are kept as the engine gives them
  (rubric lines inside the Oratio) and marked. Lenten `Preces Feriales` are present at Lauds and Vespers.
* **Completeness:** for every hour and date (including the Triduum), the words in the response equal the engine's own text with its markup removed, in both languages.
  Nothing is added, dropped or reordered.
* **Latin/English alignment:** in every row the Latin and English line counts match, except rows the engine itself gives non-parallel text for: the Martyrology
  at Prime (Sunday, Christmas, Ascension) and one Matins reading at Christmas. Those rows are flagged `aligned: false`, shown whole, and not forced into line pairs.
* **Same as upstream's own run:** the wrapper's output is byte-for-byte the same text (ignoring whitespace) as running upstream's `officium.pl` directly, checked for Matins,
  Lauds, Prime, Terce and Vespers on five dates. Compline is covered by the earlier whole-response tests and still passes unchanged.
* **Failure handling:** every hour returns 503 with the reason when the engine is not configured; an empty answer, an answer with no rows, a row without both languages, and a failing
  engine process are each reported, not hidden.

**Limits.** These checks prove the module faithfully carries what the upstream engine produces, hour by hour. They do **not** compare the result with a printed 1960
Breviary (I have none and did not attempt it); correctness of upstream's rubrical decisions (occurrence, concurrence, commemorations, Triduum) is taken from upstream.
I did not review every date of the year, nor every possible occurrence (for example transferred feasts, vigils with commemorations at None, or Tenebrae in detail).
The Triduum Offices have no ordinary headings and are carried whole, with no sequence assertion beyond completeness.

## Saving prayers from the Office (Saved Prayers)

A signed-in user can save individual prayers from any of the eight hours into the existing **Saved prayers** section of The Oratory (the same place as saved devotions).

**Which units are offered.** The server identifies units from the engine's own line labels, never from layout alone (`app/divine_office/units.py`):

| Type | Boundary | Saved as | Identity |
|---|---|---|---|
| Psalm | `Psalmus N` heading plus its numbered verses (the Gloria Patri that follows is not part of it) | fixed text | `psalm:<hash of the text>` |
| Canticle (Magnificat, Benedictus, Nunc dimittis, the Old Testament canticles at Lauds) | `Canticum…` heading, its scripture reference, numbered verses; **without** its antiphon | fixed text | `canticle:<hash>` |
| Hymn | after the `Hymnus` rubric through the plain lines up to the versicle, or a whole `Hymnus` section of one row | fixed text (hymns vary by season; each variant has its own hash) | `hymn:<hash>` |
| Antiphon | the `Ant.` line directly before its psalm or canticle (the repeat after the psalm is not offered) | **date-specific** | `antiphon:<date>:<hour>:<hash>` |

A unit is offered only if the Latin and English cells have the same number of lines and the same line kinds across it, and its id is unique in that Office. **Not offered** (no Save button): chapters, scriptural and patristic/hagiographical lessons, responsories, collects, versicles, commemorations and the Martyrology. Their ends are not marked reliably (the engine mixes them with versicles, responses and rubrics), so I did not guess. The Magnificat is therefore saved as the fixed canticle; its antiphon is a separate, dated item.

**Persistence.** Table `saved_office_units` (migration **`0012_saved_office_units`**, additive, one new table; not applied to any database by this work). Unique on (user, unit key), so the same selection can never be saved twice, and a fixed prayer saved from two days is one item that keeps the provenance (hour, date) of the first save. Rows are private to their user (another user gets 404, not 403) and removed with the user.

**API** (signed-in users; declared before the dated routes): `GET /api/divine-office/saved`, `POST /api/divine-office/saved` (body: `date`, `hour`, `unit_id` and nothing else; any other field is rejected), `GET /api/divine-office/saved/{id}`, `DELETE /api/divine-office/saved/{id}`. The client sends only a reference. The server recomputes that Office from the engine, finds the unit by id (404 if the Office does not offer it) and **snapshots the text itself**; no client text or HTML is ever stored. A snapshot is stored (not just a reference) so a saved prayer reopens unchanged if upstream changes, works without the engine, and records the upstream commit and version it came from. The cost: the translation text is held in the user's own record. Translation rights are unverified (see below); the snapshot is private, per user, and carries the same attribution and caveat.

**Frontend.** A small bookmark beside the first line of each offered prayer (English, Latin and side-by-side views; in side-by-side it appears once, in the Latin column), filled when saved, labelled for assistive technology (for example "Save to Saved Prayers: Psalm 4"). It saves and unsaves in place. If the saved list cannot be loaded, no controls are shown and the Office says saving is unavailable. Saved items appear under "Saved prayers" with title, type, hour and date, and open on `/divine-office/saved/:id`, which shows the snapshot in the chosen language(s) with its source, a link back to that hour, and a Remove button.

**Applying the migration (not done).** The Saved list and saving need the table: `cd backend; alembic upgrade head` against the local database. Until then those endpoints answer 500 and the page shows "Saving prayers is not available on this server."; everything else is unaffected.

## Licensing and provenance findings

* The repository's `LICENSE` and `README.md` state the **MIT licence** (Copyright (c) 2026 Divinum Officium) for the repository. The software may be used and
  redistributed under MIT, with the notice kept.
* **Texts:** the repository does not itemize the provenance or redistribution rights of its Latin and English texts (no per-text attribution file, and no
  mention of the English psalter or other translations in the README, docs or the English data files I searched). The MIT notice covers the repository
  as a whole; **the rights of individual translations are unverified.** Do not infer that the English is public domain. For that reason the checkout is not
  vendored or redistributed here, and every response carries a source block saying so.
* Source attribution shown in the app: Divinum Officium, version, commit, licence, and the translation-rights caveat.

## What remains

* An independent check of the output against a printed 1960 Breviary or Ordo, for a wider range of dates.
* Packaging: a production deploy would need Perl, the checkout and its dependencies on the server (a container image), or a build-time export of the days needed. Not done; local only.
* Matins is long (up to 117 KB of engine HTML on a I class feast): responses are cached in memory (64 entries) but each first request runs the engine (about 0.4 to 0.8 s here).
* Season names are derived from the engine's season code by prefix (a label only; the raw code is returned too). Resumed Sundays after Epiphany in October to
  December are labelled "Time after Pentecost (Sundays after Epiphany resumed)".
* Resolving the translation-rights question, or choosing another English source with known rights (see above).
