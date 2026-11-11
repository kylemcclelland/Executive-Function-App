# Latin prayer normalization: before and after

Editorial normalization `latin-normalization-v1` of the user-supplied transcription (`latin_prayers_file.txt`, 3022 bytes, SHA-256 `0e9258a9fff356bef4ed34438c8716cad03ce1c5cc08cd54f0de6f82dd777a8c`).
The original file in Downloads is unchanged, and the original verbatim transcription is preserved in `backend/scripts/seed_data/user_supplied_latin.json`.
Only the corrections you authorized were applied. **Nothing was verified, approved or published**, and a corrected text still needs its own review. Hidden characters and trailing spaces are shown as ‹…› markers below.

## Applied (authorized)

| Prayer | Corrections | Original SHA-256 | Normalized SHA-256 |
|---|---|---|---|
| our-father | trailing whitespace removed (1); CRLF line endings → LF | `963aac39ec5fb0db…` | `388268a723cc553a…` |
| hail-mary | soft hyphen U+00AD removed (1); comma added after “gratia plena” (1); trailing whitespace removed (3); CRLF line endings → LF | `a5047589f80445e6…` | `34b6cb4506afe859…` |
| apostles-creed | space added after a comma (2); CRLF line endings → LF | `7d346d763eeabfda…` | `f58c919265f15245…` |
| glory-be | CRLF line endings → LF | `0d9fce21c56f28d0…` | `9a5d54ef18024601…` |
| the-angelus | “Iesus” → “Jesus” (3); CRLF line endings → LF | `41df00c908ed0eba…` | `56e58e48302986e1…` |
| regina-caeli | CRLF line endings → LF | `ed1a520aa8729e88…` | `f5a0e5662e52268b…` |

Punctuation evidence for the comma after “gratia plena”: Compendium of the Catechism of the Catholic Church (Libreria Editrice Vaticana, 2005), Appendix A: Common Prayers, the Latin Ave Maria (consulted for punctuation only; nothing is reproduced). It prints a comma after “plena”. The 1889 Missale Romanum (Pustet) prints a colon there, which is liturgical punctuation, not a comma.

### our-father

```diff
-Amen ‹trailing space›
+Amen
```

### hail-mary

```diff
-Ave Maria, gratia plena
+Ave Maria, gratia plena,
-benedicta tu in mulieri‹U+00AD›bus, ‹trailing space›
+benedicta tu in mulieribus,
-ora pro nobis peccatoribus, ‹trailing space›
+ora pro nobis peccatoribus,
-nunc et in hora mortis nostrae. ‹trailing space›
+nunc et in hora mortis nostrae.
```

### apostles-creed

```diff
-ascendit ad caelos,sedet ad dexteram Dei Patris omnipotentis,
+ascendit ad caelos, sedet ad dexteram Dei Patris omnipotentis,
-sanctorum communionem,remissionem peccatorum,
+sanctorum communionem, remissionem peccatorum,
```

### glory-be

No line changed apart from CRLF → LF.

### the-angelus

```diff
-Ave Maria, gratia plena, Dominus tecum. Benedicta tu in mulieribus, et benedictus fructus ventris tui, Iesus. Sancta Maria, Mater Dei, ora pro nobis peccatoribus, nunc et in hora mortis nostrae. Amen.
+Ave Maria, gratia plena, Dominus tecum. Benedicta tu in mulieribus, et benedictus fructus ventris tui, Jesus. Sancta Maria, Mater Dei, ora pro nobis peccatoribus, nunc et in hora mortis nostrae. Amen.
-Ave Maria, gratia plena, Dominus tecum. Benedicta tu in mulieribus, et benedictus fructus ventris tui, Iesus. Sancta Maria, Mater Dei, ora pro nobis peccatoribus, nunc et in hora mortis nostrae. Amen.
+Ave Maria, gratia plena, Dominus tecum. Benedicta tu in mulieribus, et benedictus fructus ventris tui, Jesus. Sancta Maria, Mater Dei, ora pro nobis peccatoribus, nunc et in hora mortis nostrae. Amen.
-Ave Maria, gratia plena, Dominus tecum. Benedicta tu in mulieribus, et benedictus fructus ventris tui, Iesus. Sancta Maria, Mater Dei, ora pro nobis peccatoribus, nunc et in hora mortis nostrae. Amen.
+Ave Maria, gratia plena, Dominus tecum. Benedicta tu in mulieribus, et benedictus fructus ventris tui, Jesus. Sancta Maria, Mater Dei, ora pro nobis peccatoribus, nunc et in hora mortis nostrae. Amen.
```

### regina-caeli

No line changed apart from CRLF → LF.

## Proposed, NOT applied (for your review)

| Prayer | Now | Proposed | Why | Source |
|---|---|---|---|---|
| apostles-creed | “Et in Iesum Christum” | “Et in Jesum Christum” | Consistency with the authorized Iesus → Jesus. This is a different grammatical form (the accusative), so it was not changed automatically. | Owner's standardization; the Vatican Compendium (2005) prints “Iesum”. |
| regina-caeli | “Domini nostri Iesu Christi” | “Domini nostri Jesu Christi” | Consistency with the authorized Iesus → Jesus. This is the genitive “Iesu”, a different form, so it was not changed automatically. | Owner's standardization; the Vatican Compendium (2005) prints “Iesu”. |
| hail-mary | “Sancta Maria mater Dei,” | “Sancta Maria, Mater Dei,” | A comma after the vocative “Maria” and a capital M in “Mater”. This changes capitalisation and punctuation, so it needs your decision. | Compendium 2005, Appendix A prints “Sancta Maria, Mater Dei”; so does the Angelus in the same file you supplied. |
| hail-mary | “Ave Maria,” | “Ave, Maria,” | A comma after “Ave”. Optional: many traditional editions omit it. | Compendium 2005, Appendix A prints “Ave, Maria”; the 1889 Missale Romanum prints “Ave Maria”. |
| hail-mary | one phrase per paragraph, no end punctuation (“Dominus tecum”, “benedicta tu in mulieribus,”) | full sentences with capitals, as in the Angelus copy (“Dominus tecum. Benedicta tu in mulieribus, …”) | The two copies of the Hail Mary in your file are laid out differently. Decide whether they should match. | Your own Angelus text in the same file. |
| pater-noster | “Amen” with no full stop (our-father), against “Amen.” elsewhere in the file | “Amen.” | A trivial inconsistency, left as supplied. | Your own file. |
| all | consonantal “i” (eius, iudicare, Iesum, Iesu) beside the authorized “Jesus” | “ejus”, “judicare”, “Jesum”, “Jesu”, or revert to “Iesus” | After Iesus → Jesus the Latin mixes the “J” and “I” conventions. Older ecclesiastical printings use “j” throughout; the Vatican Compendium (2005) uses “i” throughout, including “Iesus”. Decide which convention you want. | Compendium 2005 (all “i”); older printings such as the 1889 Missale Romanum (“Jesse”). |

## Reviewed and left alone (legitimate traditional variants)

- Pater noster: “panem nostrum quotidianum” is the traditional liturgical form (Luke 11:3), not the Vulgate Matthew “supersubstantialem”.
- Glory Be: sparse commas (“Gloria Patri et Filio et Spiritui Sancto”) and a semicolon are both found; punctuation varies by edition.
- Creed: “caelos/caeli/caelis” use the “ae” spelling consistently (older printings use “coelos”); “descendit ad inferos” and “carnis resurrectionem” are the standard wording.
- Angelus and Regina Caeli: the versicles, responses and collects read as the traditional texts; “Genetricem” and “Genitrix” are both correct in their places.
