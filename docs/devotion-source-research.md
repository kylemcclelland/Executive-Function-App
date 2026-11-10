# Devotion source research (phase 2)

How the wording for the ten foundational devotions was sourced, what its reproduction rights are, and what is still unresolved.
**No prayer wording in this repository was written, recalled, translated or completed by an AI.** Every stored wording was copied
programmatically from a fetched source page (start and end markers in the page, HTML turned into text and nothing else), then
re-verified independently: each body was matched against the saved page, its SHA-256 re-computed, and the characters checked for
anything that leaked in from the page. Where reproduction rights are not clearly established the text is held as a **citation and
link only**, with its wording empty.

Each text record stores the SHA-256 of the saved source page and of the copied wording (in its rights notes), plus the date it was
copied, so a reviewer can check it. The saved pages themselves are kept outside the repository because several are pages whose
owners restrict reproduction.

## Rights findings

| Source | Finding | Basis |
|---|---|---|
| **Vatican** (Compendium of the Catechism 2005, *Rosarium Virginis Mariae*, Directory on Popular Piety) | **Restricted.** Wording withheld. | vatican.va legal notes: "The reproduction and collection of Contents for reasons other than personal use is expressly prohibited in the absence of prior authorization issued in writing by the DPC." The Compendium carries "(c) Copyright 2005 - Libreria Editrice Vaticana". |
| **USCCB** (Basic Prayers, Prayers of the Rosary, Act of Contrition, Examination of Conscience) | **Restricted.** Wording withheld. | No permission found on usccb.org; the only terms located say not to copy or make unauthorised uses. The examination is a one-page PDF (2013) that permits duplication only "without adaptation for non-commercial use" and embeds New American Bible text that is not licensed. The live site answered scripted requests with a bot check (not bypassed), so archive.org copies were used. |
| **Public domain** (five books on Project Gutenberg) | **Public domain in the USA.** Wording used. | Each Gutenberg record states "Public domain in the USA". Each book was first published in the US or Dublin before 1931. |

The five public-domain books: *Baltimore Catechism No. 1* (1885 imprimatur), *Baltimore Catechism No. 3* (Benziger, 1921), Gahan,
*The Complete Manual of Catholic Piety* (Dublin, 1844), Lings, *Our Monthly Devotions* (Benziger, 1899), Hammer, *General Catholic
Devotions* (Benziger, 1909).

## What is available, per devotion and language

"Wording" means sourced wording is held. "Citation only" means a source is cited and linked but its wording is withheld.
"None" means no record exists, because no real source was found.

| Devotion | English | Latin |
|---|---|---|
| Sign of the Cross | Wording (Baltimore No. 1) | Wording (Lings 1899, the opening of the Mass) |
| Our Father | Wording (Baltimore No. 1) | Citation only (Compendium) |
| Hail Mary | Wording (Baltimore No. 1) | Citation only (Compendium) |
| Glory Be | Wording (Baltimore No. 1) | Citation only (Compendium) |
| Apostles' Creed | Wording (Baltimore No. 1) | Citation only (Compendium) |
| The Angelus | Wording (Baltimore No. 3, Q. 44) | Citation only (Compendium) |
| The Holy Rosary: Hail, Holy Queen | Wording (Gahan 1844) | Wording (Lings 1899) |
| The Holy Rosary: concluding prayer | Wording (Gahan 1844) | Citation only (Compendium) |
| The Holy Rosary: Fátima prayer (optional) | None | None |
| Examination of Conscience | Citation only (USCCB, 2013) | None (not researched) |
| Act of Contrition | Wording (Baltimore No. 1) | Citation only (Compendium) |
| Prayer to St. Michael | Wording (Hammer 1909) | None |

12 texts hold sourced wording and 8 are citation-only. Latin and English are **separate records with separate sources**; neither
is derived from the other.

## Things a reviewer should know before approving

* **The English is the older Baltimore and Irish English** ("Holy Ghost", "Thee/Thy", "trespasses"), not the modern USCCB wording,
  because the modern wording's rights are not cleared. Decide whether that is the form you want.
* **No source names a translator.** The English prayers are flagged as translations (they originate in Latin or Greek), and the
  translator field says "Translator not named in the source" rather than inventing a name.
* **Apostles' Creed (Baltimore No. 1)** reads "I believe in the Holy Ghost the Holy Catholic Church" with no comma after "Ghost":
  that is exactly how the source transcription prints it.
* **The Angelus (Baltimore No. 3, Q. 44)** abbreviates each Hail Mary as "Hail Mary, &c." and has no versicle or response labels.
  It was compared with an independent 1921 scan (only OCR differences). A better public-domain edition exists (the 1888 *Manual of
  Prayers*, with Latin and English side by side and V./R. labels) but its OCR loses decorated initials and interleaves the
  columns, so it needs a proofread transcription from page images.
* **Baltimore No. 1** prints no copyright page, so its date rests on the 1885 imprimatur and on the sister volume's notices.
* **Public-domain status outside the United States** was not checked for any of the five books.
* **Hail, Holy Queen (Gahan 1844)** reads "poor banished sons of Eve"; a more familiar form in Hammer 1909 was skipped because
  its transcription capitalises the opening words.
* The Latin Sign of the Cross comes from the rubric where the priest begins the Mass.

## Unresolved

* **Latin texts** for the Our Father, Hail Mary, Glory Be, Creed, Angelus, the Rosary collect and the Act of Contrition: no cleared
  source was found. The best source (the Compendium prints Latin beside English) needs written Vatican permission; the 1888
  Manual of Prayers (public domain) needs a proofread transcription.
* **Latin Prayer to St. Michael:** a Latin Wikisource page exists but cites no edition; pre-1931 *Raccolta* editions on
  archive.org are the next place to look.
* **Fátima prayer:** no pre-1931 source was found.
* **Examination of Conscience:** needs written USCCB permission, or an original examination you approve.

## Structure sources (citations only; nothing copied)

* John Paul II, *Rosarium Virginis Mariae* (2002): the Luminous mysteries are named in n. 21; the method in nn. 26-37; the suggested
  days in n. 38 (and the next paragraph says they are not meant to limit freedom of prayer). Nn. 22-23 discuss the Sorrowful
  and Glorious mysteries in narrative form without listing them.
* *Compendium of the Catechism of the Catholic Church* (2005), Appendix A, "The Rosary": names all twenty mysteries and their days.
* *Directory on Popular Piety and the Liturgy*, nn. 195-196: the Angelus and the Regina Caeli in Eastertide; nn. 197-202: the Rosary.
* USCCB "How to Pray the Rosary": not read (the live site returns a bot check and no archive copy was found).
