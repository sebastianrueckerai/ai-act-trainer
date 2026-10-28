from unittest.mock import patch

from langchain_core.messages import AIMessage

from app.graph.state import (
    ChapterDonePart,
    ChapterStartPart,
    Choice,
    CitationPart,
    FilePart,
    InputHint,
    ModelAnswerCard,
    TurnScratch,
    initial_state,
)
from app.graph.translate import parts_from_dumps, render_en, translate_node, translate_text
from tests.fakes.scripted import ScriptedChatModel


def _citation(ref: str) -> CitationPart:
    return CitationPart(ref=ref, title="Artikel 4", quote="Zitat", url="https://eur-lex.europa.eu/")


def _state(display_locale: str, text: str, parts=(), hint=None):
    state = initial_state(persona_id="pirate", display_locale=display_locale)
    message = AIMessage(text, id="m1", additional_kwargs={"parts": []})
    turn = TurnScratch(draft=text, parts=list(parts), input_hint=hint or InputHint(kind="text"))
    return {**state, "messages": [message], "turn": turn}


def test_german_sessions_are_left_alone(make_deps):
    deps = make_deps(script={})
    assert translate_node(deps)(_state("de", "Guten Tag.")) == {}
    assert deps.models["fast"].calls == []


def _rendering(result: dict) -> dict:
    [message] = result["messages"]
    return message.additional_kwargs["en"]


def test_the_translation_rides_along_the_german_stays_the_message(make_deps):
    deps = make_deps(script={"translate": "Good day.\n\nRead Art. 5(1)(f)."})
    result = translate_node(deps)(_state("en", "Guten Tag.\n\nLies Art. 5 Abs. 1 Buchst. f."))
    [message] = result["messages"]
    assert message.id == "m1"
    # The German stays the stored truth; the flag flip serves either side.
    assert message.content == "Guten Tag.\n\nLies Art. 5 Abs. 1 Buchst. f."
    assert message.additional_kwargs["en"]["text"] == "Good day.\n\nRead Art. 5(1)(f)."
    assert message.additional_kwargs["parts"] == []
    assert set(result) == {"messages"}
    assert deps.models["fast"].calls == ["translate"]


def test_card_fields_and_choices_are_rendered_and_the_german_state_is_left_alone(make_deps):
    card = ModelAnswerCard(
        question="Frage?",
        model_answer="Antwort.",
        explanation="Weil.",
        citations=[_citation("Art. 4 Abs. 1")],
        correct=True,
    )
    hint = InputHint(kind="choices", choices=[Choice(key="A", label="Ja, darf ich.")])
    deps = make_deps(
        script={
            "translate": "Hello.",
            "translate_fields": (
                "1: Question?\n2: Answer.\n3: Because.\n4: Article 4\n5: Yes, I may."
            ),
        }
    )
    state = _state("en", "Hallo.", parts=[card], hint=hint)
    result = translate_node(deps)(state)
    rendering = _rendering(result)
    [rendered_card] = rendering["parts"]
    assert (
        rendered_card["question"],
        rendered_card["model_answer"],
        rendered_card["explanation"],
    ) == ("Question?", "Answer.", "Because.")
    assert rendering["hint"]["choices"][0]["label"] == "Yes, I may."
    assert "turn" not in result and "last_hint" not in result
    assert state["turn"].parts[0].question == "Frage?"
    assert state["turn"].input_hint.choices[0].label == "Ja, darf ich."
    assert "Art." not in deps.models["fast"].prompts[-1]


def test_card_citations_are_rendered_in_english_without_asking_the_model(make_deps):
    card = ModelAnswerCard(
        question="Q?",
        model_answer="A.",
        explanation="E.",
        citations=[_citation("Art. 4 Abs. 1"), _citation("Q&A der Kommission 14")],
        correct=True,
    )
    deps = make_deps(
        script={"translate": "Hi.", "translate_fields": "1: Q?\n2: A.\n3: E.\n4: Art 4\n5: Art 4"}
    )
    result = translate_node(deps)(_state("en", "Hallo.", parts=[card]))
    [rendered_card] = _rendering(result)["parts"]
    assert [c["ref"] for c in rendered_card["citations"]] == ["Art. 4(1)", "Q&A 14"]
    assert deps.models["fast"].calls == ["translate", "translate_fields"]


def test_citation_part_refs_are_rendered_in_english_without_asking_the_model(make_deps):
    part = CitationPart(ref="BDSG § 26(1)", title="§ 26", quote="Text.", url="https://x")
    deps = make_deps(script={"translate": "Hi.", "translate_fields": "1: Section 26"})
    result = translate_node(deps)(_state("en", "Hallo.", parts=[part]))
    [rendered_part] = _rendering(result)["parts"]
    assert rendered_part["ref"] == "Section 26(1) BDSG"
    assert rendered_part["title"] == "Section 26"
    assert deps.models["fast"].calls == ["translate", "translate_fields"]


def test_the_node_streams_the_rendering_it_stores(make_deps):
    hint = InputHint(kind="confirm", label="Ja, weiter", asks=False)
    deps = make_deps(script={"translate": "Hello.", "translate_fields": "1: Yes, go on"})
    written: list[dict] = []
    with patch("app.graph.translate.get_stream_writer", return_value=written.append):
        result = translate_node(deps)(_state("en", "Hallo.", hint=hint))
    en = _rendering(result)
    assert written[0] == {"type": "token", "text": "Hello."}
    assert written[-1] == {"type": "input_hint", "hint": en["hint"]}
    assert en["hint"]["label"] == "Yes, go on"


def test_the_first_message_streams_its_body_and_stores_the_greeting_once(make_deps):
    deps = make_deps(script={"translate": "First lesson."})
    state = _state("en", "Guten Tag.\n\nErste Lektion.")
    state["opening_line"] = "Guten Tag."
    state["opening_line_en"] = "Good day."
    written: list[dict] = []
    with patch("app.graph.translate.get_stream_writer", return_value=written.append):
        result = translate_node(deps)(state)
    assert written[0] == {"type": "token", "text": "First lesson."}
    assert _rendering(result)["text"] == "Good day.\n\nFirst lesson."
    assert deps.models["fast"].prompts[0].endswith("Erste Lektion.")


def test_a_card_only_turn_stays_empty_instead_of_asking_the_model_for_text(make_deps):
    """A step's answer card carries the whole reply; the message text is "" by design
    (app/graph/test_flow.py's _advance leaves turn.draft unset). Without a guard, the
    live model answers the empty prompt conversationally instead of translating nothing."""
    card = ModelAnswerCard(
        question="Frage?",
        model_answer="Antwort.",
        explanation="Weil.",
        citations=[],
        correct=True,
    )
    deps = make_deps(
        script={
            "translate": "I'm ready to translate, but I need the German text first.",
            "translate_fields": "1: Question?\n2: Answer.\n3: Because.",
        }
    )
    written: list[dict] = []
    with patch("app.graph.translate.get_stream_writer", return_value=written.append):
        result = translate_node(deps)(_state("en", "", parts=[card]))
    assert result["messages"][0].content == ""
    assert _rendering(result)["text"] == ""
    assert deps.models["fast"].calls == ["translate_fields"]
    assert written[0]["type"] != "token"


def test_a_missing_number_keeps_the_german_field(make_deps):
    hint = InputHint(
        kind="choices", choices=[Choice(key="A", label="Ja."), Choice(key="B", label="Nein.")]
    )
    deps = make_deps(script={"translate": "Hi.", "translate_fields": "1: Yes."})
    result = translate_node(deps)(_state("en", "Hallo.", hint=hint))
    assert [c["label"] for c in _rendering(result)["hint"]["choices"]] == ["Yes.", "Nein."]


def test_translate_text_masks_citations_and_restores_them_in_english(make_deps):
    model = ScriptedChatModel(script={"translate": "As ⟦1⟧ requires.\n\nSee also ⟦2⟧ and ⟦3⟧."})
    german = "Nach Art. 4 Abs. 1 gilt das.\n\nSiehe auch Art. 26 Abs. 7 und Q&A der Kommission 14."
    result = translate_text(model, german)
    assert result == "As Art. 4(1) requires.\n\nSee also Art. 26(7) and Q&A 14."
    [prompt] = model.prompts
    assert "Art. 4 Abs. 1" not in prompt
    assert "⟦1⟧" in prompt


def test_translate_text_drops_a_citation_the_model_invented():
    model = ScriptedChatModel(script={"translate": "Good day. (Art. 5(1)(f)) Have a nice read."})
    result = translate_text(model, "Guten Tag. Viel Spaß beim Lesen.")
    assert result == "Good day. Have a nice read."


def test_translate_text_leaves_no_stray_token_for_one_the_model_dropped():
    model = ScriptedChatModel(script={"translate": "First point.\n\nThird point mentions ⟦3⟧."})
    german = (
        "Erster Punkt, siehe Art. 4 Abs. 1.\n\n"
        "Zweiter Punkt, siehe Art. 26 Abs. 7.\n\n"
        "Dritter Punkt erwähnt Q&A der Kommission 14."
    )
    result = translate_text(model, german)
    assert result == "First point.\n\nThird point mentions Q&A 14."
    assert "⟦" not in result


def test_render_en_renders_text_parts_and_hint_in_two_calls() -> None:
    card = ModelAnswerCard(
        question="Darf ich?",
        model_answer="Ja.",
        explanation="Weil.",
        citations=[CitationPart(ref="Art. 4", title="KI-Kompetenz", quote="…", url="u")],
        correct=True,
    )
    line = CitationPart(
        ref="Art. 5 Abs. 1 Buchst. f", title="Verbotene Praktiken", quote="Zitat", url="u2"
    )
    sheet = FilePart(url="/api/files/x", title="Spickzettel Kapitel 1", filename="k1.pdf")
    hint = InputHint(
        kind="choices",
        choices=[Choice(key="a", label="Ja, darf ich."), Choice(key="b", label="Nein.")],
        label="Ja, weiter",
        asks=True,
    )
    model = ScriptedChatModel(
        script={
            "translate": "May I?",
            "translate_fields": "\n".join(
                [
                    "1: May I?",
                    "2: Yes.",
                    "3: Because.",
                    "4: AI literacy",
                    "5: Prohibited practices",
                    "6: Cheat sheet chapter 1",
                    "7: Yes, I may.",
                    "8: No.",
                    "9: Yes, go on",
                ]
            ),
        }
    )

    rendering = render_en(model, "Darf ich?", [card, line, sheet], hint)

    assert rendering["text"] == "May I?"
    assert model.calls == ["translate", "translate_fields"]
    rendered_card, rendered_line, rendered_sheet = rendering["parts"]
    assert rendered_card["kind"] == "card"
    assert (
        rendered_card["question"],
        rendered_card["model_answer"],
        rendered_card["explanation"],
    ) == ("May I?", "Yes.", "Because.")
    assert rendered_card["citations"][0]["ref"] == "Art. 4"
    assert rendered_card["citations"][0]["title"] == "AI literacy"
    assert rendered_line["ref"] == "Art. 5(1)(f)"
    assert rendered_line["title"] == "Prohibited practices"
    assert rendered_line["quote"] == "(Original, Deutsch) Zitat"
    assert rendered_sheet == {
        "kind": "file",
        "url": "/api/files/x",
        "title": "Cheat sheet chapter 1",
        "filename": "k1.pdf",
    }
    assert [c["label"] for c in rendering["hint"]["choices"]] == ["Yes, I may.", "No."]
    assert rendering["hint"]["label"] == "Yes, go on"
    assert rendering["hint"]["kind"] == "choices"


def test_render_en_renders_the_chapter_marks_in_place() -> None:
    start = ChapterStartPart(title="Was du hineingeben darfst", intro="Eine Frage jeden Tag.")
    sheet = FilePart(url="/api/files/x", title="Spickzettel Kapitel 1", filename="k1.pdf")
    done = ChapterDonePart(chapter_id="01-a", index=1, total=8, title="Was du darfst")
    model = ScriptedChatModel(
        script={
            "translate": "Text.",
            "translate_fields": "\n".join(
                [
                    "1: Cheat sheet chapter 1",
                    "2: What you may do",
                    "3: What you may put in",
                    "4: One question every day.",
                    "5: On to chapter 2",
                ]
            ),
        }
    )

    rendering = render_en(
        model, "Text.", [start, sheet, done], InputHint(kind="confirm", label="Weiter zu Kapitel 2")
    )

    assert rendering["parts"] == [
        {
            "kind": "chapter_start",
            "title": "What you may put in",
            "intro": "One question every day.",
        },
        {
            "kind": "file",
            "url": "/api/files/x",
            "title": "Cheat sheet chapter 1",
            "filename": "k1.pdf",
        },
        {
            "kind": "chapter_done",
            "chapter_id": "01-a",
            "index": 1,
            "total": 8,
            "title": "What you may do",
        },
    ]
    assert rendering["hint"]["label"] == "On to chapter 2"
    assert parts_from_dumps(rendering["parts"])[::2] == [
        start.model_copy(
            update={"title": "What you may put in", "intro": "One question every day."}
        ),
        done.model_copy(update={"title": "What you may do"}),
    ]


def test_render_en_without_a_hint_returns_a_null_hint_and_asks_nothing_for_it() -> None:
    model = ScriptedChatModel(script={"translate": "Hi."})
    rendering = render_en(model, "Hallo.", [], None)
    assert rendering == {"text": "Hi.", "parts": [], "hint": None}
    assert model.calls == ["translate"]


def test_parts_from_dumps_reads_stored_display_parts_back() -> None:
    dumps = [
        {
            "kind": "card",
            "question": "Q",
            "model_answer": "A",
            "explanation": "E",
            "citations": [
                {
                    "kind": "citations",
                    "ref": "Art. 4 Abs. 1",
                    "title": "T",
                    "quote": "Z",
                    "url": "u",
                }
            ],
            "correct": False,
            "tries": 2,
        },
        {"kind": "citations", "ref": "Art. 3 Nr. 1", "title": "T2", "quote": "Z2", "url": "u2"},
        {"kind": "file", "url": "/f", "title": "S", "filename": "s.pdf"},
    ]
    card, line, sheet = parts_from_dumps(dumps)
    assert isinstance(card, ModelAnswerCard)
    assert card.tries == 2 and card.citations[0].ref == "Art. 4 Abs. 1"
    assert isinstance(line, CitationPart) and line.ref == "Art. 3 Nr. 1"
    assert isinstance(sheet, FilePart) and sheet.filename == "s.pdf"
