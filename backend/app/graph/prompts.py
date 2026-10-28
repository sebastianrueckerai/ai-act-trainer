TRIAGE = "[node:triage]"
COMPACT = "[node:compact]"
FREE_QUESTION = "[node:free_question]"
HELP = "[node:help]"
PERSONA = "[node:persona]"
GRADE = "[node:grade]"
REPLY = "[node:reply]"
CRITIC = "[node:critic]"
VOICE_CRITIC = "[node:voice_critic]"
PROSE = "[node:prose]"
SHORTEN = "[node:shorten]"
TRANSLATE = "[node:translate]"
TRANSLATE_FIELDS = "[node:translate_fields]"


def mark(prompt: str, marker: str) -> str:
    """The node marker opens the prompt, where a model is least likely to echo it back."""
    return f"{marker}\n\n{prompt}"


CITE_RULE = (
    "The law's citations have exactly these written forms: Art. 26(7), Art. 5(1)(f), "
    "Annex III pt. 4(a), Rec. 44, GDPR Art. 5(1)(a), BDSG § 26(1), BetrVG § 87(1) Nr. 6, "
    "KI-MIG § 2(1), Q&A 14. These are forms, not pointers: name an article only when the "
    "tools or the brief put it in the turn. "
    "Never invent a rule. If no bundled act covers it, say exactly "
    "what the trainer may say instead. Never a national law's name in front of its "
    "paragraph in another order (not 'DSGVO Art. 5(1)(a)'), never the abbreviation 'pt.' "
    "translated or dropped, never a space before the parenthesised paragraph (not "
    "'Art. 26 (7)')."
)

PLAIN_TEXT_RULE = (
    "Write plain German prose, paragraphs separated by a blank line. No Markdown: "
    "no headings, no #, no **, no bullet or numbered lists, no tables, no horizontal rules, "
    "no code fences. The student reads this in a chat bubble that renders none of it."
)

NODE_ID_RULE = (
    "The law tools return internal node ids built from an act key and short tags: cpt, sct, "
    "art, anx, rec, and forms like 'ai_act cpt IV' or 'ai_act art 26'. Those tags are "
    "internal. Never write cpt, sct, art, anx, rec or an act key to the student, alone or "
    "with a number, and never mix a written form with a raw tag: 'Kapitel III sct 2' is a "
    "fault. Write 'Kapitel IV', 'Artikel 26', 'Anhang III', 'Abschnitt 2' or "
    "'Erwägungsgrund 44', and cite with the written forms above."
)

GENDER_RULE = (
    "Write German with the generic masculine only: Nutzer, Betreiber, Anbieter, "
    "Mitarbeiter, Kollegen. No gender stars, colons, underscores, middle dots or slashes "
    "(Nutzer*in, Nutzer:in, Nutzer/innen), no Binnen-I (NutzerIn), no paired forms "
    "(Nutzerinnen und Nutzer), no participle substitutes (Mitarbeitende, Studierende)."
)

EXPERTISE_RULES = (
    "Expertise rules:\n"
    "- The bundled acts define what you may answer. Answer from them in plain words: never "
    "quote the act's own wording, and never write a citation inside a sentence. End the reply "
    'with one line that opens "Fundstellen: " and names the citations you relied on, '
    'comma-separated, the way a German reader writes them ("Fundstellen: Art. 4 Abs. 1, '
    'Art. 5 Abs. 1 Buchst. f"). The app shows that line as the sources under the reply.\n'
    "- No bundled act covers the question: say you are an AI Act trainer and do not know "
    "this, and invent no rule.\n"
    "- No disclaimers beyond that. One trainer-not-lawyer line is added elsewhere when "
    "the student asks about their own case.\n"
    "- The conclusion comes first, in one sentence: what the student may or must do. Then "
    "at most three short paragraphs with the reason, the condition and the example. The "
    "student wants the answer, not the derivation.\n"
    "- When the student asks whether they may do something at work, answer as the "
    "employee's question: whether they may do it on their own, who in the company decides "
    "and whom to ask. 'Yes, if you meet the deployer's duties' is wrong for an employee who "
    "is not the deployer: an employee may not start a high-risk use on their own "
    "initiative.\n"
    "- Prefer the German word where German has one: 'Mensch in der Schleife' instead of "
    "'Human-in-the-Loop', 'bestmöglich' instead of 'Best-Effort', 'Werkzeug' instead of "
    "'Tool'. The law's own terms stay as the law writes them: KI-System, Anbieter, "
    "Betreiber, Hochrisiko-KI-System, KI-Kompetenz.\n"
    f"- {CITE_RULE}\n"
    f"- {NODE_ID_RULE}\n"
    f"- {PLAIN_TEXT_RULE}\n"
    f"- {GENDER_RULE}"
)

ANSWER_LENGTH_RULE = "Answer in at most three short paragraphs, the conclusion first."

ANSWER_IN_LOCALE = (
    "Write your whole answer in the locale named in the prompt. The law's own terms keep the "
    "German form the law gives them: KI-System, Anbieter, Betreiber, Hochrisiko-KI-System."
)

TRANSLATE_RULE = (
    "Translate the German tutor message below into English. Keep the character's voice, "
    "keep every paragraph break, keep every number. Tokens written ⟦1⟧, ⟦2⟧ "
    "and so on are law citations already in place: keep each exactly where it stands, "
    "unchanged, and add no citation or reference of your own. Return only the translation, "
    "no preface."
)

TRANSLATE_FIELDS_RULE = (
    "Translate every numbered German field below into English, one line per number, the "
    "same numbering, nothing else. Keep every option letter and every number. Add no "
    "citation or reference of your own. Return only the numbered list, no preface."
)
