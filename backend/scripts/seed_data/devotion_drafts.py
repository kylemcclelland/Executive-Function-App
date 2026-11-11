# ruff: noqa: E501
"""The ten foundational devotions, as unpublished editorial drafts.

This module holds STRUCTURE and short explanatory prose only. It contains no prayer wording: wording comes from
prayer_sources.json, where every text carries its source and rights, and where a text whose reproduction rights
are not cleared is held as a citation with no wording.

The explanatory prose (overviews and instructions) was drafted with AI assistance. Every record is marked
``prose_origin = "ai_draft"``, so the review screens label it "Unapproved editorial prose" until an approver has
approved the devotion. Nothing here is approved or published, and seeding never overwrites an existing record.
"""

CREATED_BY = "seed:devotion-drafts-v1"
PROSE_ORIGIN = "ai_draft"

RVM = "https://www.vatican.va/content/john-paul-ii/en/apost_letters/2002/documents/hf_jp-ii_apl_20021016_rosarium-virginis-mariae.html"
COMPENDIUM = "https://www.vatican.va/archive/compendium_ccc/documents/archive_2005_compendium-ccc_en.html"
DIRECTORY = "https://www.vatican.va/roman_curia/congregations/ccdds/documents/rc_con_ccdds_doc_20020513_vers-direttorio_en.html"
USCCB_EXAM = "https://www.usccb.org/resources/Examination-of-Conscience-Ten-Commandments.pdf"


def draft(code, slug, title, category, subtitle, overview, instructions=(), minutes=None, references=(), steps=(), choice_label=None, history=None, purpose=None):
    return {
        "code": code, "slug": slug, "title": title, "category": category, "subtitle": subtitle,
        "estimated_minutes": minutes, "overview": overview, "background": history, "significance": purpose,
        "references": [dict(label=label, url=url) for label, url in references],
        "instructions": list(instructions), "steps": list(steps), "choice_label": choice_label,
    }


# ---- The Holy Rosary: structure only. Every prayer is reused from its own devotion, never copied. -------------------
SETS = [
    ("Joyful Mysteries", ["The Annunciation", "The Visitation", "The Nativity", "The Presentation", "The Finding in the Temple"]),
    ("Luminous Mysteries", ["The Baptism of Jesus", "The Wedding Feast at Cana", "The Proclamation of the Kingdom", "The Transfiguration", "The Institution of the Eucharist"]),
    ("Sorrowful Mysteries", ["The Agony in the Garden", "The Scourging at the Pillar", "The Crowning with Thorns", "The Carrying of the Cross", "The Crucifixion"]),
    ("Glorious Mysteries", ["The Resurrection", "The Ascension", "The Descent of the Holy Spirit", "The Assumption", "The Coronation of Mary"]),
]
ORDINALS = ["First", "Second", "Third", "Fourth", "Fifth"]


def prayer(title, slot, owner=None, repeat=None, section=None, group=None, optional=False, instruction=None, kind="prayer"):
    return {"kind": kind, "title": title, "instruction": instruction, "text_slot": slot, "devotion_slug": owner, "repeat": repeat, "section": section, "group": group, "optional": optional}


def note(title, instruction, section=None, group=None):
    return {"kind": "instruction", "title": title, "instruction": instruction, "text_slot": None, "devotion_slug": None, "repeat": None, "section": section, "group": group, "optional": False}


def rosary_steps():
    steps = [
        prayer("Sign of the Cross", "main", "sign-of-the-cross", section="Opening prayers"),
        prayer("Apostles’ Creed", "main", "apostles-creed", section="Opening prayers"),
        prayer("Our Father", "main", "our-father", section="Opening prayers"),
        prayer("Three Hail Marys", "main", "hail-mary", repeat=3, section="Opening prayers", optional=True, instruction="A common custom, not part of the core Rosary."),
        prayer("Glory Be", "main", "glory-be", section="Opening prayers"),
    ]
    for name, mysteries in SETS:
        for number, mystery in enumerate(mysteries):
            where = f"{name}: {ORDINALS[number].lower()} decade"
            steps += [
                note(f"{number + 1}. {mystery}", "Recall this mystery of the life of Jesus and Mary before you begin the decade.", where, name),
                prayer("Our Father", "main", "our-father", section=where, group=name),
                prayer("Hail Mary", "main", "hail-mary", repeat=10, section=where, group=name),
                prayer("Glory Be", "main", "glory-be", section=where, group=name),
                prayer("Fátima prayer", "fatima-prayer", section=where, group=name, optional=True, instruction="An optional custom after each decade, not part of the core Rosary."),
            ]
    steps += [
        prayer("Hail, Holy Queen", "hail-holy-queen", section="Concluding prayers"),
        prayer("Concluding prayer", "rosary-concluding-prayer", section="Concluding prayers"),
        prayer("Sign of the Cross", "main", "sign-of-the-cross", section="Concluding prayers", optional=True, instruction="Many conclude with the Sign of the Cross."),
    ]
    return steps


DRAFTS = [
    draft(
        "DEV-001", "sign-of-the-cross", "Sign of the Cross", "Daily Prayer",
        "A short prayer that begins and ends other prayers",
        "The Sign of the Cross is a brief prayer made by tracing a cross on the body while naming the Holy Trinity. Catholics use it to begin and end prayer, and it is made at the start of Mass.",
        ["Make the sign slowly, with attention to what you are doing.",
         "Many people trace the cross with the right hand, touching the forehead, chest and shoulders. Customs for the exact gesture vary; follow the practice of your community.",
         "Traditional occasions: at the start and end of prayer, at the start of Mass, on entering a church, before meals, and at the beginning and end of the day."],
        minutes=1,
        history="Early Christian writers describe tracing a cross on the forehead as a habitual gesture; Tertullian, writing around AD 200, mentions it. Forms that name the Father, the Son and the Holy Spirit developed over the following centuries.",
        purpose="It recalls Baptism and the cross of Christ, and places prayer and daily actions under the name of the Holy Trinity.",
        references=[("Tertullian, De corona militis, 3 (citation to be verified by the reviewer)", None), ("Catechism of the Catholic Church, no. 2157 (citation to be verified by the reviewer)", None)]),
    draft(
        "DEV-002", "our-father", "Our Father", "Our Lord",
        "The prayer Jesus taught his disciples",
        "The Our Father, also called the Lord’s Prayer, is the prayer that Jesus teaches his disciples in the Gospels of Matthew and Luke. It is prayed at Mass, in the Church’s daily prayer and in the Rosary.",
        ["Pray it slowly, a phrase at a time.",
         "Translations and traditions end it in slightly different ways; the wording shown is exactly as it appears in the source cited with it.",
         "Traditional occasions: at Mass, in Morning and Evening Prayer, in the Rosary, and in personal prayer at any time."],
        minutes=1,
        history="The prayer appears in two forms in the Gospels, in Matthew 6:9–13 and Luke 11:2–4. It has been used in the Church’s worship and instruction from the earliest centuries; the Didache, an early Christian text, directs that it be prayed three times a day.",
        purpose="It is the prayer the Lord himself gave to his disciples, and the Catechism of the Catholic Church devotes its final part to it.",
        references=[("Gospel of Matthew 6:9–13", None), ("Gospel of Luke 11:2–4", None), ("Didache, 8 (citation to be verified by the reviewer)", None), ("Catechism of the Catholic Church, nos. 2759–2865", None)]),
    draft(
        "DEV-003", "hail-mary", "Hail Mary", "Our Lady",
        "A greeting to Mary and a request for her prayers",
        "The Hail Mary greets Mary with words from the Gospel of Luke and then asks for her prayers. It is the prayer repeated in the Rosary and in the Angelus.",
        ["Pray it slowly.",
         "Traditional occasions: in the Rosary and the Angelus, and in personal prayer, especially at morning, evening and in need."],
        minutes=1,
        history="The first part joins the angel’s greeting to Mary (Luke 1:28) and Elizabeth’s greeting (Luke 1:42). The petition that follows was added in later centuries, and the prayer reached its present form in the Roman Breviary of 1568.",
        purpose="It greets Mary as the Gospel does and asks for her prayers now and at the hour of death.",
        references=[("Gospel of Luke 1:28 and 1:42", None), ("Roman Breviary of 1568, on the standard form of the prayer (citation to be verified by the reviewer)", None)]),
    draft(
        "DEV-004", "glory-be", "Glory Be", "Daily Prayer",
        "A short prayer of praise to the Holy Trinity",
        "The Glory Be, in Latin the Gloria Patri, is a short prayer of praise to the Father, the Son and the Holy Spirit. It is said at the end of the psalms in the Church’s daily prayer and at the end of each decade of the Rosary.",
        ["It is often prayed with a slight bow of the head.",
         "Traditional occasions: at the end of each psalm in the Liturgy of the Hours, at the end of each decade of the Rosary, and at the close of other prayers."],
        minutes=1,
        history="A short Trinitarian doxology of praise, used to close the psalms in Christian prayer from the early centuries, in forms that developed through the Trinitarian controversies of the fourth century.",
        purpose="It gives praise to the Father, the Son and the Holy Spirit, and turns any prayer toward the glory of God.",
        references=[("General Instruction of the Liturgy of the Hours, on the doxology at the end of psalms (paragraph to be located by the reviewer)", None)]),
    draft(
        "DEV-005", "apostles-creed", "Apostles’ Creed", "Daily Prayer",
        "A summary of the Christian faith",
        "The Apostles’ Creed is a short statement of the Christian faith in three parts, on the Father, the Son and the Holy Spirit. It is an ancient profession of faith and it begins the Rosary. Its name reflects an old tradition connecting it with the teaching of the Apostles.",
        ["At Mass the Nicene Creed is usually professed; the Apostles’ Creed may be used in its place, particularly in Lent and the Easter season. Praying it elsewhere is a devotion, not a requirement.",
         "Traditional occasions: at the start of the Rosary, in the renewal of baptismal promises, and in personal prayer as a profession of faith."],
        minutes=1,
        history="It developed from the baptismal profession of faith of the early Roman Church. Its present form is found by about the eighth century. The tradition that each of the twelve Apostles contributed one article is a later one.",
        purpose="It gathers the Church’s baptismal faith in the Father, the Son and the Holy Spirit into a short profession that can be prayed by heart.",
        references=[("Catechism of the Catholic Church, nos. 194–197 (citation to be verified by the reviewer)", None)]),
    draft(
        "DEV-006", "the-angelus", "The Angelus", "Our Lady",
        "A traditional prayer recalling the Incarnation, prayed three times a day",
        "The Angelus is a traditional prayer that recalls the Incarnation. It is customarily prayed three times a day, at morning, noon and evening, often at the ringing of a bell. In the Easter season the Regina Caeli is traditionally prayed in its place.",
        ["The prayer is made of short verses and responses, each followed by a Hail Mary, and ends with a concluding prayer.",
         "Where the text reads “Hail Mary, &c.”, the Hail Mary is prayed. Its wording is in the Hail Mary devotion.",
         "It is a traditional private devotion, not a required one.",
         "Traditional occasions: at dawn, at midday and at dusk, with the Regina Caeli in its place in the Easter season."],
        minutes=3,
        history="A medieval devotion rooted in the custom of reciting Hail Marys at the ringing of a bell, extended over time from the evening to morning and midday.",
        purpose="It recalls the Incarnation, when the Word became flesh, and sanctifies the three main points of the day.",
        references=[("Directory on Popular Piety and the Liturgy, nn. 195–196", DIRECTORY), ("History of the bell and the three daily prayers (source to be located by the reviewer)", None)]),
    draft(
        "DEV-007", "regina-caeli", "Regina Caeli", "Our Lady",
        "The Marian prayer of the Easter season, prayed in place of the Angelus",
        "The Regina Caeli (Queen of Heaven) is a traditional Marian prayer that rejoices with Mary in the Resurrection of her Son. In the Easter season it is prayed in place of the Angelus.",
        ["It is made of short verses with responses and a concluding prayer.",
         "Traditional occasions: at morning, noon and evening during the Easter season, in the place of the Angelus.",
         "It is a traditional private devotion, not a required one."],
        minutes=2,
        history="Pope Benedict XIV directed in 1742 that the Regina Caeli be said in place of the Angelus in the Easter season.",
        purpose="It shares Mary's joy in the Resurrection of Christ.",
        references=[("Directory on Popular Piety and the Liturgy, nn. 195–196", DIRECTORY)]),
    draft(
        "DEV-008", "the-holy-rosary", "The Holy Rosary", "Our Lady",
        "A prayer on the mysteries of the life of Jesus and Mary",
        "The Rosary is a traditional Catholic prayer in which the Our Father, ten Hail Marys and a Glory Be are prayed in each of five decades while recalling a mystery from the life of Jesus and Mary. The mysteries are grouped in four sets: the Joyful, the Luminous (proposed by Pope John Paul II in 2002), the Sorrowful and the Glorious. The Rosary is a private devotion that the Church commends; it is not obligatory.",
        ["Choose a set of mysteries. A suggested pattern is Joyful on Monday and Saturday, Luminous on Thursday, Sorrowful on Tuesday and Friday, and Glorious on Wednesday and Sunday. It is a suggestion, not a requirement.",
         "Begin with the opening prayers, then pray the five decades of your chosen set, then the concluding prayers.",
         "For each decade, recall the mystery, then pray one Our Father, ten Hail Marys and one Glory Be.",
         "Beads are an aid to attention. You may pray one decade or the whole Rosary; there is nothing to complete or to report to anyone.",
         "Customs such as the Fátima prayer after each decade, or three Hail Marys at the opening, are marked as optional and are not part of the core Rosary."],
        minutes=20, choice_label="Mysteries", steps=rosary_steps(),
        references=[("John Paul II, Rosarium Virginis Mariae (2002), nn. 19–21 and 37–38", RVM),
                    ("Compendium of the Catechism of the Catholic Church (2005), Appendix A: Common Prayers, The Rosary", COMPENDIUM)]),
    draft(
        "DEV-009", "examination-of-conscience", "Examination of Conscience", "Daily Prayer",
        "A quiet, reasonable look at one’s life before God",
        "An examination of conscience is a prayerful review of one’s thoughts, words and actions in the light of the Gospel. Before the Sacrament of Penance it helps a person recall what to confess, often using the Ten Commandments as a guide. A daily examen is a shorter and gentler review of the day, giving thanks and asking for light; it is not the same as preparing for Confession.",
        ["Begin by asking for God’s light and mercy.",
         "Read slowly and honestly, but peacefully. This is a reasonable review, not a search for perfect certainty, and it is not meant to produce anxiety.",
         "If you are troubled by worry about whether you have sinned, speak with a priest.",
         "The specific published examination cited here is held as a citation only, because its reproduction rights are not cleared."],
        minutes=10,
        references=[("A Brief Examination of Conscience Based on the Ten Commandments, United States Conference of Catholic Bishops (2013)", USCCB_EXAM),
                    ("Compendium of the Catechism of the Catholic Church, Q. 303: the acts of the penitent", COMPENDIUM)]),
    draft(
        "DEV-010", "act-of-contrition", "Act of Contrition", "Daily Prayer",
        "A prayer of sorrow for sin and trust in God’s mercy",
        "An Act of Contrition is a prayer that expresses sorrow for sin, trust in God’s mercy and the intention to amend one’s life. Several forms are in use. One is prayed by the penitent in the Sacrament of Penance, and it may also be prayed at the end of the day.",
        ["Pray it from the heart. In Confession, follow the priest’s guidance about which form to use."],
        minutes=1),
    draft(
        "DEV-011", "prayer-to-st-michael", "Prayer to St. Michael", "Saints",
        "A prayer asking the Archangel Michael’s help against evil",
        "The Prayer to St. Michael the Archangel asks for his help and protection in spiritual struggle. A form of it was widely prayed after Low Mass from the late nineteenth century.",
        ["Pray it slowly. It is a traditional private devotion."],
        minutes=1),
]
