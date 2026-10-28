from lxml import html

from app.corpus.textutil import split_label, text_of


def test_text_of_drops_footnote_refs_and_markers_and_normalizes_spaces():
    fragment = html.fromstring(
        '<div><p class="modref"><a>▼M1</a></p>'
        '<p>Providers\xa0shall<a href="#E0001" id="src.E0001">'
        '<span class="superscript">1</span></a> '
        "take   measures.</p></div>"
    )
    assert text_of(fragment) == "Providers shall take measures."


def test_split_label_handles_numbers_letters_and_roman():
    assert split_label("1.\xa0\xa0Text") == ("1", "Text")
    assert split_label("(a) Text") == ("a", "Text")
    assert split_label("(ba) Text") == ("ba", "Text")
    assert split_label("(iv) Text") == ("iv", "Text")
    assert split_label("No label") == ("", "No label")


def test_split_label_handles_the_german_and_amended_marker_forms():
    assert split_label("a) Text") == ("a", "Text")
    assert split_label("(1)\xa0\xa0Text") == ("1", "Text")
    assert split_label("1a.\xa0\xa0Text") == ("1a", "Text")
    assert split_label("(14a) Text") == ("14a", "Text")
    assert split_label("„(3)\xa0\xa0Text") == ("3", "Text")
    assert split_label("—") == ("", "—")
    assert split_label("(20) Text") == ("20", "Text")
