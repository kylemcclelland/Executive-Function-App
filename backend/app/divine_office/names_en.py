# ruff: noqa: E501
"""English names for the temporal (non-saint) celebrations of the 1960 calendar, by deterministic rules.

Divinum Officium's English data has no English titles for Sundays, ferias, octave days and vigils (its English "Tempora" files carry the Latin
title), so these are translated here from the regular Latin patterns of those titles, with established English liturgical terminology. A title that
no rule matches exactly is NOT translated: the caller keeps the Latin and flags it. Nothing is guessed and no language model is involved.
"""

import re

ORDINALS = {n: w for n, w in enumerate(
    ["", "First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth", "Ninth", "Tenth", "Eleventh", "Twelfth", "Thirteenth", "Fourteenth", "Fifteenth",
     "Sixteenth", "Seventeenth", "Eighteenth", "Nineteenth", "Twentieth", "Twenty-first", "Twenty-second", "Twenty-third", "Twenty-fourth", "Twenty-fifth"])}
ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50}
DAYS = {"secunda": "Monday", "tertia": "Tuesday", "quarta": "Wednesday", "quinta": "Thursday", "sexta": "Friday", "ii": "Monday", "iii": "Tuesday", "iv": "Wednesday", "v": "Thursday", "vi": "Friday", "sabbato": "Saturday"}
MONTHS = {"septembris": "September", "octobris": "October", "novembris": "November", "augusti": "August", "decembris": "December"}
# What a week is "of" or "after": the established English phrase for each Latin season word.
WEEK_OF = {
    "in quadragesima": "of Lent", "adventus": "of Advent", "post epiphaniam": "after Epiphany", "post octavam paschae": "after the Octave of Easter",
    "post octavam pentecostes": "after the Octave of Pentecost", "passionis": "of Passiontide", "septuagesimae": "of Septuagesima", "sexagesimae": "of Sexagesima", "quinquagesimae": "of Quinquagesima",
}
OCTAVE_OF = {
    "paschae": "Easter", "pentecostes": "Pentecost", "nativitatis": "the Nativity", "epiphaniae": "Epiphany", "ascensionis": "the Ascension", "corporis christi": "Corpus Christi",
    "s. joseph": "St. Joseph", "ssmi cordis jesu": "the Most Sacred Heart of Jesus", "sanctissimi corporis christi": "Corpus Christi", "ssmi cordis d.n.j.c": "the Most Sacred Heart of Jesus",
}
VIGIL_OF = {"ascensionis": "the Ascension", "pentecostes": "Pentecost", "epiphaniae": "Epiphany", "nativitatis domini": "the Nativity of Our Lord"}
FIXED = {
    "dominica resurrectionis": "Easter Sunday", "dominica pentecostes": "Pentecost Sunday", "dominica sanctissimae trinitatis": "Trinity Sunday",
    "dominica in albis in octava paschae": "Low Sunday (Octave Day of Easter)", "sabbato in albis": "Saturday in White (within the Octave of Easter)",
    "dominica de passione": "Passion Sunday", "dominica in palmis": "Palm Sunday", "dominica in septuagesima": "Septuagesima Sunday", "dominica in sexagesima": "Sexagesima Sunday",
    "dominica in quinquagesima": "Quinquagesima Sunday", "sabbato sancto": "Holy Saturday", "feria quinta in cena domini": "Holy Thursday", "feria sexta in parasceve": "Good Friday",
    "dominica i passionis": "Passion Sunday", "dominica ii passionis seu in palmis": "Palm Sunday", "feria sexta in passione et morte domini": "Good Friday",
    "feria iv cinerum": "Ash Wednesday", "sabbato post cineres": "Saturday after Ash Wednesday", "in ascensione domini": "Ascension of Our Lord",
    "in octava ascensionis": "Octave Day of the Ascension", "in octava sanctissimi corporis christi": "Octave Day of Corpus Christi", "in octava ssmi cordis jesu": "Octave Day of the Most Sacred Heart of Jesus",
    "festum sanctissimi corporis christi": "Corpus Christi", "sanctissimi nominis jesu": "Most Holy Name of Jesus", "sacratissimi cordis domini nostri jesu christi": "Most Sacred Heart of Our Lord Jesus Christ",
    "sanctae familiae jesu mariae joseph": "Holy Family of Jesus, Mary and Joseph", "septem dolorum beatae mariae virginis": "Seven Sorrows of the Blessed Virgin Mary",
    "dominica post ascensionem": "Sunday after the Ascension", "dominica infra octavam epiphaniae": "Sunday within the Octave of Epiphany", "dominica infra octavam nativitatis": "Sunday within the Octave of the Nativity", "dominica infra octavam ascensionis": "Sunday within the Octave of the Ascension",
    "sabbato infra octavam ascensionis": "Saturday within the Octave of the Ascension",
}


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("æ", "ae").replace("Æ", "Ae").replace("œ", "oe")).strip().lower()


def roman(value: str) -> int | None:
    total, previous = 0, 0
    for char in reversed(value.upper()):
        if char not in ROMAN:
            return None
        number = ROMAN[char]
        total += number if number >= previous else -number
        previous = max(previous, number)
    return total


def ordinal(value: str) -> str | None:
    number = roman(value)
    return ORDINALS.get(number) if number else None


def designation(suffix: str, base: str) -> str | None:
    """The Breviary's month designation, in the Breviary's own numbering: not a civil date.

    The liturgical month begins with the Sunday on or nearest the 1st; for November the weeks are counted back from Advent and, under the 1960 rubrics, the
    II week is omitted. So 8 November 2026 (the second Sunday of the civil month) is "III. Novembris" and is labelled the Third Sunday of November (Breviary numbering).
    """
    found = re.fullmatch(r"\s*([ivx]+)\.?\s+(\w+)\s*", normalize(suffix))
    if not found or found.group(2) not in MONTHS or not ordinal(found.group(1)):
        return None
    unit = "Sunday" if base.startswith("dominica") else "Week"
    return f"{ordinal(found.group(1))} {unit} of {MONTHS[found.group(2)]} (Breviary numbering)"


def translate(name_latin: str) -> tuple[str, str | None] | None:
    """(English name, the month designation of a Sunday if it has one), or None when no rule matches the whole title exactly."""
    text = normalize(name_latin)
    note = None
    month = re.fullmatch(r"(.+?)\s+([ivx]+\.? (?:septembris|octobris|novembris|augusti|decembris))", text)
    if month:
        text, note = month.group(1), designation(month.group(2), month.group(1))
        if note is None:
            return None
    if text in FIXED:
        return FIXED[text], note
    rules = [
        (r"dominica ([ivx]+) post epiphaniam", lambda m: f"{ordinal(m[1])} Sunday after Epiphany"),
        (r"dominica ([ivx]+) post pentecosten", lambda m: f"{ordinal(m[1])} Sunday after Pentecost"),
        (r"dominica ([ivx]+) et ultima post pentecosten", lambda m: f"{ordinal(m[1])} and Last Sunday after Pentecost"),
        (r"dominica ([ivx]+) post pentecosten infra octavam (.+)", lambda m: f"{ordinal(m[1])} Sunday after Pentecost, within the Octave of {OCTAVE_OF[m[2]]}" if m[2] in OCTAVE_OF else None),
        (r"dominica ([ivx]+) adventus", lambda m: f"{ordinal(m[1])} Sunday of Advent"),
        (r"dominica ([ivx]+) in quadragesima", lambda m: f"{ordinal(m[1])} Sunday of Lent"),
        (r"dominica ([ivx]+) post pascha", lambda m: f"{ordinal(m[1])} Sunday after Easter"),
        (r"(?:feria )?(secunda|tertia|quarta|quinta|sexta|ii|iii|iv|v|vi|sabbato)(?: (?:secunda|tertia|quarta|quinta|sexta))? infra hebdomadam ([ivx]+) (in quadragesima|adventus|post epiphaniam|post octavam paschae|post octavam pentecostes)",
         lambda m: f"{DAYS[m[1]]} of the {ordinal(m[2])} Week {WEEK_OF[m[3]]}"),
        (r"(?:feria )?(secunda|tertia|quarta|quinta|sexta|ii|iii|iv|v|vi|sabbato) in hebdomadam ([ivx]+) (adventus)", lambda m: f"{DAYS[m[1]]} of the {ordinal(m[2])} Week {WEEK_OF[m[3]]}"),
        (r"(?:feria )?(secunda|tertia|quarta|quinta|sexta|ii|iii|iv|v|vi|sabbato) infra hebdomadam (passionis|septuagesimae|sexagesimae|quinquagesimae)",
         lambda m: f"{DAYS[m[1]]} of {'Passion Week' if m[2] == 'passionis' else WEEK_OF[m[2]].replace('of ', '') + ' Week'}"),
        (r"(?:feria )?(secunda|tertia|quarta|ii|iii|iv) majoris hebdomadae", lambda m: f"{DAYS[m[1]]} of Holy Week"),
        (r"feria (secunda|tertia|quarta) hebdomadae sanctae", lambda m: f"{DAYS[m[1]]} of Holy Week"),
        (r"die (secunda|tertia|quarta|quinta) januarii", lambda m: f"January {({'secunda': 2, 'tertia': 3, 'quarta': 4, 'quinta': 5})[m[1]]}"),
        (r"feria (v|vi) post cineres", lambda m: f"{DAYS[m[1]]} after Ash Wednesday"),
        (r"(?:die|diei|de) ([ivx]+)(?: die)? infra octavam (.+)", lambda m: f"{ordinal(m[1])} Day within the Octave of {OCTAVE_OF[m[2]]}" if m[2] in OCTAVE_OF and ordinal(m[1]) else None),
        (r"die (secunda|tertia|quarta|quinta|sexta|septima) infra octavam (.+)", lambda m: f"{ORDINALS[{'secunda': 2, 'tertia': 3, 'quarta': 4, 'quinta': 5, 'sexta': 6, 'septima': 7}[m[1]]]} Day within the Octave of {OCTAVE_OF[m[2]]}" if m[2] in OCTAVE_OF else None),
        (r"(?:feria )?(secunda|tertia|quarta|quinta|sexta|ii|iii|iv|v|vi|sabbato) infra octavam (.+)", lambda m: f"{DAYS[m[1]]} within the Octave of {OCTAVE_OF[m[2]]}" if m[2] in OCTAVE_OF else None),
        (r"feria (secunda|tertia) in rogationibus", lambda m: f"Rogation {DAYS[m[1]]}"),
        (r"feria quarta in rogationibus in vigilia ascensionis", lambda m: "Rogation Wednesday, Vigil of the Ascension"),
        (r"(?:feria )?(quarta|sexta|iv|vi) quattuor temporum (septembris|pentecostes|quadragesimae|in adventu|adventus)", lambda m: f"Ember {DAYS[m[1]]} of {({'septembris': 'September', 'pentecostes': 'Pentecost', 'quadragesimae': 'Lent', 'in adventu': 'Advent', 'adventus': 'Advent'})[m[2]]}"),
        (r"sabbato quattuor temporum (septembris|pentecostes|quadragesimae|in adventu|adventus)", lambda m: f"Ember Saturday of {({'septembris': 'September', 'pentecostes': 'Pentecost', 'quadragesimae': 'Lent', 'in adventu': 'Advent', 'adventus': 'Advent'})[m[1]]}"),
        (r"(?:feria )?(secunda|tertia|quarta|quinta|sexta|ii|iii|iv|v|vi) infra hebdomadam post ascensionem", lambda m: f"{DAYS[m[1]]} in the week after the Ascension"),
        (r"sabbato in vigilia pentecostes", lambda m: "Saturday, Vigil of Pentecost"),
        (r"in vigilia (.+)", lambda m: f"Vigil of {VIGIL_OF[m[1]]}" if m[1] in VIGIL_OF else None),
    ]
    for pattern, build in rules:
        found = re.fullmatch(pattern, text)
        if found:
            try:
                english = build(found)
            except KeyError:
                return None
            return (english, note) if english and "None" not in english else None       # an unknown ordinal (not in the table) is never printed
    return None
