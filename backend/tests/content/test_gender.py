import pytest

from app.content.gender import degender, find_gendered

PLURAL_SEP_CASES = [
    ("Nutzer*innen", "Nutzer"),
    ("Nutzer:innen", "Nutzer"),
    ("Nutzer_innen", "Nutzer"),
    ("Nutzer·innen", "Nutzer"),
    ("Nutzer/-innen", "Nutzer"),
    ("Nutzer/innen", "Nutzer"),
    ("NutzerInnen", "Nutzer"),
    ("Betreiber*innen", "Betreiber"),
    ("Anbieter:innen", "Anbieter"),
    ("Mitarbeiter_innen", "Mitarbeiter"),
    ("Arbeitgeber·innen", "Arbeitgeber"),
    ("Bewerber/innen", "Bewerber"),
    ("Kolleg*innen", "Kollegen"),
    ("Expert:innen", "Experten"),
    ("Kund_innen", "Kunden"),
    ("Jurist·innen", "Juristen"),
    ("Autor/innen", "Autoren"),
    ("Ärzt*innen", "Ärzte"),
    ("Anwält:innen", "Anwälte"),
    ("Köch_innen", "Köche"),
    ("Bäuer·innen", "Bauern"),
    ("Chef/innen", "Chefs"),
    ("Ingenieur*innen", "Ingenieure"),
    ("Beamt:innen", "Beamte"),
    ("Freund_innen", "Freunde"),
]


@pytest.mark.parametrize("text,expected", PLURAL_SEP_CASES)
def test_plural_forms_are_found_and_rewritten(text: str, expected: str) -> None:
    assert find_gendered(text) == [text]
    assert degender(text) == expected


SINGULAR_SEP_CASES = [
    ("Nutzer*in", "Nutzer"),
    ("Kolleg:in", "Kollege"),
    ("Expert_in", "Experte"),
    ("Kund·in", "Kunde"),
    ("NutzerIn", "Nutzer"),
    ("Ärzt*in", "Arzt"),
    ("Anwält:in", "Anwalt"),
    ("Köch_in", "Koch"),
    ("Bäuer·in", "Bauer"),
    ("Chef/in", "Chef"),
    ("Ingenieur*in", "Ingenieur"),
    ("Beamt:in", "Beamter"),
    ("Freund_in", "Freund"),
]


@pytest.mark.parametrize("text,expected", SINGULAR_SEP_CASES)
def test_singular_forms_are_found_and_rewritten(text: str, expected: str) -> None:
    assert find_gendered(text) == [text]
    assert degender(text) == expected


def test_binnen_i_plural_and_singular_are_mutually_exclusive() -> None:
    assert find_gendered("NutzerInnen") == ["NutzerInnen"]
    assert degender("NutzerInnen") == "Nutzer"
    assert find_gendered("NutzerIn") == ["NutzerIn"]
    assert degender("NutzerIn") == "Nutzer"


def test_hyphenated_compound_stem_is_covered() -> None:
    assert degender("KI-Expert*innen") == "KI-Experten"


PRONOUN_CASES = [
    ("jede*r", "jeder"),
    ("jede:r", "jeder"),
    ("jede_r", "jeder"),
    ("ein*e", "ein"),
    ("ein:e", "ein"),
    ("eine*n", "einen"),
    ("eine:n", "einen"),
    ("der*die", "der"),
    ("die*der", "der"),
    ("der/die", "der"),
    ("die/der", "der"),
    ("er*sie", "er"),
    ("sie*er", "er"),
    ("er/sie", "er"),
    ("sie/er", "er"),
]


@pytest.mark.parametrize("text,expected", PRONOUN_CASES)
def test_pronoun_and_article_forms_are_rewritten(text: str, expected: str) -> None:
    assert find_gendered(text) == [text]
    assert degender(text) == expected


def test_pronoun_capitalisation_is_preserved() -> None:
    assert degender("Er/sie kommt gleich.") == "Er kommt gleich."
    assert degender("Jede*r kennt das.") == "Jeder kennt das."


PAIR_CASES = [
    ("Nutzerinnen und Nutzer", "Nutzer"),
    ("Nutzer und Nutzerinnen", "Nutzer"),
    ("Kolleginnen und Kollegen", "Kollegen"),
    ("Mitarbeiterinnen und Mitarbeiter", "Mitarbeiter"),
    ("Nutzerin oder Nutzer", "Nutzer"),
    ("Nutzer oder Nutzerin", "Nutzer"),
    ("Nutzerinnen bzw. Nutzer", "Nutzer"),
]


@pytest.mark.parametrize("text,expected", PAIR_CASES)
def test_paired_forms_collapse_to_the_masculine_word(text: str, expected: str) -> None:
    assert find_gendered(text) == [text]
    assert degender(text) == expected


def test_unrelated_pair_is_never_matched() -> None:
    text = "Kunden und Lieferanten arbeiten zusammen."
    assert find_gendered(text) == []
    assert degender(text) == text


PARTICIPLE_REWRITE_CASES = [
    ("Mitarbeitende", "Mitarbeiter"),
    ("Mitarbeitenden", "Mitarbeiter"),
    ("Nutzende", "Nutzer"),
    ("Teilnehmende", "Teilnehmer"),
    ("Studierende", "Studenten"),
]


@pytest.mark.parametrize("text,expected", PARTICIPLE_REWRITE_CASES)
def test_participle_bare_plural_form_is_rewritten(text: str, expected: str) -> None:
    assert find_gendered(text) == [text]
    assert degender(text) == expected


PARTICIPLE_INFLECTED_CASES = [
    "Mitarbeitender",
    "Mitarbeitendes",
    "Mitarbeitendem",
    "Nutzendem",
    "Teilnehmenden",
    "Studierenden",
]


@pytest.mark.parametrize("text", PARTICIPLE_INFLECTED_CASES)
def test_participle_inflected_forms_are_reported_but_not_rewritten(text: str) -> None:
    assert find_gendered(text) == [text]
    assert degender(text) == text


def test_beschaeftigte_is_never_flagged() -> None:
    text = "Die Beschäftigten haben eigene Rechte."
    assert find_gendered(text) == []
    assert degender(text) == text


ARTICLE_FIX_CASES = [
    ("eine Nutzer*in", "ein Nutzer"),
    ("einer Nutzer*in", "einem Nutzer"),
    ("die Nutzer*in", "der Nutzer"),
    ("jede Nutzer*in", "jeder Nutzer"),
    ("jeder Nutzer*in", "jedem Nutzer"),
    ("keine Nutzer*in", "kein Nutzer"),
    ("keiner Nutzer*in", "keinem Nutzer"),
    ("meine Nutzer*in", "mein Nutzer"),
    ("deine Nutzer*in", "dein Nutzer"),
    ("unsere Nutzer*in", "unser Nutzer"),
    ("ihre Nutzer*in", "ihr Nutzer"),
    ("seine Nutzer*in", "sein Nutzer"),
]


@pytest.mark.parametrize("text,expected", ARTICLE_FIX_CASES)
def test_feminine_determiner_before_a_singular_is_fixed(text: str, expected: str) -> None:
    assert degender(text) == expected


def test_determiner_fix_examples_from_the_spec() -> None:
    assert degender("eine Nutzer*in") == "ein Nutzer"
    assert degender("jede*r Nutzer*in") == "jeder Nutzer"
    assert degender("die Kolleg:in") == "der Kollege"


def test_determiner_fix_preserves_capitalisation() -> None:
    assert degender("Eine Nutzer*in kam vorbei.") == "Ein Nutzer kam vorbei."


def test_already_masculine_determiner_is_left_alone() -> None:
    assert degender("der Nutzer*in") == "der Nutzer"


NON_MATCH_CASES = [
    "Er arbeitet in der Firma.",
    "Berlin ist die Hauptstadt.",
    "innen und außen",
    "Der Termin ist morgen.",
    "Medizin ist ein Fach.",
    "Art. 26(7) gilt hier.",
    "Mehr dazu unter https://example.com/innen",
    "bzw. das reicht schon.",
    "This is English text with no gendering at all.",
]


@pytest.mark.parametrize("text", NON_MATCH_CASES)
def test_things_that_must_never_be_touched(text: str) -> None:
    assert find_gendered(text) == []
    assert degender(text) == text


def test_sentence_initial_innen_is_not_matched() -> None:
    text = "Innen ist es wärmer als außen."
    assert find_gendered(text) == []
    assert degender(text) == text


def test_find_gendered_returns_forms_verbatim_and_in_order() -> None:
    text = "Nutzer*innen und Kolleg:in und jede*r."
    assert find_gendered(text) == ["Nutzer*innen", "Kolleg:in", "jede*r"]


FULLY_FIXABLE_CASES = [
    "Die Nutzer*innen und Kolleg:innen arbeiten zusammen.",
    "eine Nutzer*in",
    "jede*r Nutzer*in",
    "die Kolleg:in",
    "Nutzerinnen und Nutzer, Kolleginnen und Kollegen.",
    "Mitarbeitende sitzen im Büro.",
]


@pytest.mark.parametrize("text", FULLY_FIXABLE_CASES)
def test_degender_leaves_nothing_left_to_find(text: str) -> None:
    assert find_gendered(degender(text)) == []


IDEMPOTENT_CASES = FULLY_FIXABLE_CASES + [
    "mit den Mitarbeitenden zusammen",
    "Ein ganz normaler Satz.",
]


@pytest.mark.parametrize("text", IDEMPOTENT_CASES)
def test_degender_is_idempotent(text: str) -> None:
    once = degender(text)
    assert degender(once) == once


def test_clean_text_is_returned_unchanged() -> None:
    text = "Nutzer und Betreiber arbeiten zusammen mit Anbietern und Mitarbeitern."
    assert degender(text) == text
    assert find_gendered(text) == []
