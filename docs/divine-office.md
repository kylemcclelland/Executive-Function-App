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

## Traditional Liturgical Calendar card (Today dashboard)

`GET /api/liturgical-calendar/{date}?edition=roman_1960` (signed-in users; only `roman_1960` is accepted) returns the principal celebration of a date from the same engine and
version (`Rubrics 1960 - 1960`); the Today page shows it in a card above the priorities, with a link to that date's Divine Office. The date is the reader's **local** date (not UTC).

**What comes from the engine** (`app/divine_office/calendar.py`, one `prayMatutinum` run per date, cached 400 dates in memory, plus the already cached Lauds for commemorations):
the celebration's name and rank (the engine's own `setheadline`, "Name ~ III. classis", which the wrapper now also prints as `<!--DO-HEAD-->`), the winning office file
(`Sancti/…`, `Tempora/…`, `Commune/…`), the English name of that office, the season code, and the commemorations (the rubric lines of Lauds). Nothing is calculated here.

**Celebration types.** `saint` (a `Sancti` winner named "S./SS./B. …" that is not a feast of the Lord or Our Lady), `feast` (feasts of the Lord and Our Lady, dedications and other `Sancti` feasts),
`sunday`, `feria` and `temporal` (vigils, octave days, Ascension, … from `Tempora`), and `other` (for example Our Lady on Saturday, a `Commune` winner). Not every day has a saint: ferias and Sundays are shown as such.
Sundays and ferias show the engine's Latin name; the engine has no English name for them and none is invented.

**Descriptions: coverage and sources.** A description is offered **only for a saint's feast**, and only when the engine's own English Matins gives that saint a biographical lesson: Reading 3 of a
one-nocturn Office (the 1960 abridged legend), or Reading 4 of a three-nocturn Office, where the body follows the "Reading N" marker directly (a Scripture lesson or a sermon has a source line first).
The description is the lesson's **own opening sentences, copied verbatim** (2 or 3 sentences, 35 to 65 words; a single whole sentence in that range is kept; otherwise none), after checking that the lesson names the saint
(a word of the engine's English title appears in it), and refusing text carrying the engine's omission markup. Source recorded with each: "The Roman Breviary, Matins lesson (English), as supplied by Divinum Officium",
with the reference "Matins, Reading N, <saint> (<file>)" and the note that translation rights are not verified. Not used: any language model, any other biography, month-and-day matching alone (identity is the engine's winning office
plus the name check).

Not covered (no description is shown, only name, rank, season, commemorations): Sundays, ferias, temporal feasts, feasts of the Lord and Our Lady (their Matins lessons are Scripture and homilies, not descriptions), and saints whose lesson does not
qualify (for example most saints with nine lessons whose Reading 4 is a sermon). Alban Butler's *Lives of the Saints* was **not** used: I did not obtain a verified public-domain edition within the time limit. See the coverage figures in the project report.

Known limits: the lesson is the Breviary's account, not an independent
historical check; I did not verify the facts against another source.

**English names (refinement).** The card shows an English name and keeps the Latin title beneath it (`celebration`, `celebration_latin`), with `celebration_source` saying where the English came from:

* `upstream_english`: the engine's own English title (saints and feasts such as "St. Andrew Avellino", "Nativity of Our Lord Jesus Christ", "Assumption of the Blessed Virgin Mary"). A leading Latin abbreviation is normalised ("S. Agnes" becomes "St. Agnes").
  Where the engine's English data holds only the Latin title for the 1960 version (8 December: the 1960 `[Rank]` variant exists in the Latin file alone), the wrapper falls back to the English file's own default `[Rank]` name, read as written ("Immaculate Conception of the Blessed Virgin Mary"); nothing is translated there.
* `translated`: upstream's English files for Sundays, ferias, octave days and vigils carry the Latin title, so these are translated by fixed rules in `app/divine_office/names_en.py` (established liturgical terms: "Fifth Sunday after Epiphany",
  "Wednesday of the Second Week of Lent", "Fourth Day within the Octave of Easter", "Vigil of the Ascension", "Ember Wednesday of September", "Holy Saturday", ...). A rule applies only if it matches the **whole** title; a title it does not match is not translated.
  The rules cover 389 of the 391 temporal titles in the upstream data (a test reads them all; the other two are the Patronage titles below) and every title the engine produced for the 365 days of 2026.
* `latin_untranslated`: no rule matched, so the Latin is kept and flagged. In the 2026 scan this never happens. Two titles would stay Latin by design: `In Octava Patrocinii S. Joseph` and `Patrocinii St. Joseph Confessoris Sponsi B.M.V. Confessoris`.
  They belong to the Patronage of St. Joseph, whose upstream `[Rank]` has no 1960 entry (the feast was suppressed in 1955): under `Rubrics 1960 - 1960` the engine returns the ordinary Wednesday of those weeks instead (tested for 2025 to 2030), so the titles are not translated.


The Breviary's month designation of Sundays and weeks from September to December ("Dominica V Post Epiphaniam **III. Novembris**") is kept as `designation` and always labelled **"(Breviary numbering)"**, e.g. "Third Sunday of November (Breviary numbering)" for a Sunday and "First Week of November (Breviary numbering)" for a weekday. It is **not a civil count**: upstream (`DivinumOfficium/Date.pm`, `monthday`) starts the liturgical month with the Sunday on or nearest the 1st and, for November, counts the weeks back from Advent with the II week omitted under the 1960 rubrics. 8 November 2026, the second Sunday of the civil month, is therefore "III. Novembris".

**Saint names.** A qualifier ("Confessor", "Virgin and Martyr", "Bishop, Confessor and Doctor of the Church", "Apostles") is separated only when the boundary is unambiguous: after a comma, or after a name that does not end in "the", "of", "and" or an ordinal, and never "Martyr" without a comma (it can be a cognomen). Otherwise the whole title is kept as the name.
"St. Peter the Martyr" (29 April) and "St. Matthias the Apostle" stay whole; "St. Stephen the First Martyr" becomes "St. Stephen, the First Martyr"; "Sts. Peter and Paul, Apostles" is split at its comma. Descriptions, their identity checks and their sources are unchanged.

**One corrected upstream title.** 14 April (`Sancti/04-14.txt`) is titled `St. Justini Martyr` upstream (a Latin genitive in an English title). An exact-match rule (winner file and exact text, nothing broader) shows it as "St. Justin Martyr", keeps the Latin `S. Justini Martyris`, and records the change in `english_correction` (also shown as the heading's tooltip). A side effect: the identity check for the saint's description now matches (the lesson names Justin), so that day gained a description (112 of 137, from 111).

**Validation status (2026) and test commands.**

* Calendar: the engine's `Rubrics 1960 - 1960` (universal Roman calendar, not the 1960 "New Calendar" variant), upstream commit recorded in every response.
* **Fast, deterministic (no engine)**: `pytest tests/test_liturgical_calendar.py -k "split or classify or rank or sentences or description or temporal_titles or exact_rules"` and the computus/Ember arithmetic in `tests/test_liturgical_calendar_year.py` (`pytest tests/test_liturgical_calendar_year.py -k "computus or ember_days_of_2026 or ember_wednesdays or ash_wednesday_and_the_days"`).
* **Bounded engine checks (about 1 to 2 minutes)**: `pytest tests/test_liturgical_calendar.py tests/test_liturgical_calendar_year.py` (the exhaustive test is skipped by default). They cover representative dates, the Ember days of Lent, Pentecost, September and Advent, 23 Easter-based and fixed celebrations, the season boundaries, 14 April (St. Justin Martyr), the November designations and the Patronage-of-St.-Joseph exception.
* **Optional exhaustive check (about 8 minutes, launches the Perl engine 365 times; do not run it routinely)**: `OPTIMA_FULL_YEAR=1 pytest tests/test_liturgical_calendar_year.py -k every_day`. Every assertion in it is collected, so one run reports everything.

What the exhaustive test checks, kept apart: *faithful handling of the engine's output* (every day resolves, names well formed, Latin/rank/season/commemorations the engine's, saints-only verbatim descriptions, the exact set of saints without a description) and *independent arithmetic* (Easter-based and fixed feasts from the computus, Ember days, weekday words in ferias' titles, Sundays, season boundaries). It is **not** a comparison with a printed 1960 Breviary or Ordo, which has not been done.

**What was actually verified.** One complete 365-day run reached its final stage (all hard assertions passed for every day: well-formed names, none left in Latin where a rule exists, the one exact correction, 137 saints, exactly 25 without a description and 112 with). Its soft checks were not reported (an earlier assertion stopped it first), and no snapshot was kept, so **the independent full-year checks (anchors, weekday words, Sundays, season boundaries) have not been confirmed across all 365 dates**; the targeted tests above confirm them on the dates that matter. Other runs were killed by an engine timeout (the machine slept) or never finished.

**Ember days (1960).** Verified against the upstream engine, not assumed: Wednesday, Friday and Saturday after the first Sunday of Lent, after Pentecost, after the **third Sunday of September** (23, 25 and 26 September 2026; 16, 18 and 19 September, the pre-1960 "after 14 September" days, are ordinary saints' days) and after the **third Sunday of Advent** (16, 18, 19 December 2026). Upstream gets September from its month-week numbering (`DivinumOfficium/Date.pm`, `monthday`, which under the 1960 rubrics counts the first civil Sunday as the first of the month) and uses `Adv3`, `Quad1` and `Pasc7` for the others (`emberday`).

**Season label fix.** Upstream's season code for Quinquagesima week runs through the Saturday after Ash Wednesday, so Ash Wednesday to Saturday had been labelled "Septuagesima". They are now labelled "Lent", decided by the engine's own titles (`Feria IV Cinerum`, `post Cineres`), not by any new calculation.

**Remaining.** (1) The exhaustive independent checks above have not been completed over all 365 dates; a bounded way to finish them is to save the engine's answers once to a JSON snapshot (a script outside the test suite) and run the pure-arithmetic checks against that file. (2) Only 2026 has been examined. (3) Nothing was compared with a printed Breviary. (4) The two Patronage of St. Joseph titles stay Latin by design (never produced under 1960).

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
