from langchain_core.messages import AIMessage, HumanMessage

from app.graph.critic import Critique
from app.graph.persona import persona_node, plain_text
from app.graph.prompts import GENDER_RULE
from app.graph.state import Guard, InputHint, Mood, Phase, TurnScratch, initial_state
from app.i18n import t

QUESTION_ID = "q-02-04"
DRAFT = "Richtig, das ist erlaubt.\n\nAber was passiert mit dem Entwurf, bevor er rausgeht?"
VOICED = (
    "Hört, hört! Erlaubt ist es.\n\n"
    "Aber was geschieht mit dem Entwurf, ehe er das Schloss verlässt?"
)
BRIEF = "Tutor:\nThe tutor.\n\nJob:\nOutcome: partial. Confirm the part."
CLOSING = t("de", "step_prompt")
SHIP = Critique(verdict="ship", score=5)


def _state(persona_id: str, turn: TurnScratch, phase: Phase = Phase.lesson) -> dict:
    state = initial_state(persona_id)
    state["phase"] = phase
    state["mood"] = Mood.neutral
    state["turn"] = turn
    state["messages"] = [AIMessage("Was antwortest du ihr?"), HumanMessage("Ist erlaubt.")]
    return state


def _turn(draft: str = DRAFT, brief: str = BRIEF) -> TurnScratch:
    return TurnScratch(draft=draft, context_question=QUESTION_ID, brief=brief)


def test_the_rewrite_prompt_carries_the_brief_the_manifest_and_the_draft(make_deps):
    deps = make_deps(script={"persona": VOICED, "voice_critic": SHIP})
    persona_node(deps)(_state("jester", _turn()))
    prompt = deps.models["strong"].prompts[0]
    assert prompt.startswith("[node:persona]")
    assert BRIEF in prompt
    assert "Persona voice:" in prompt and "Persona style rules:" in prompt
    assert "Add no fact, no hint and no question of your own" in prompt
    assert GENDER_RULE in prompt
    assert f"The tutor's message:\n{DRAFT}" in prompt
    assert "previous rewrite" not in prompt


def test_a_rewrite_the_critic_passes_ships(make_deps):
    deps = make_deps(script={"persona": VOICED, "voice_critic": SHIP})
    result = persona_node(deps)(_state("jester", _turn()))
    assert result["messages"][0].content == VOICED
    assert deps.models["strong"].calls == ["persona", "voice_critic"]
    critic_prompt = deps.models["strong"].prompts[1]
    assert f"The tutor's draft:\n{DRAFT}" in critic_prompt
    assert f"The rewrite in the character's voice:\n{VOICED}" in critic_prompt
    assert BRIEF in critic_prompt


def test_a_rejected_rewrite_is_redone_with_its_text_and_the_notes(make_deps):
    deps = make_deps(
        script={
            "persona": [VOICED + " Und wer noch?", VOICED],
            "voice_critic": [
                Critique(
                    verdict="retry", faults=["question"], notes="Keine eigene Frage.", score=2
                ),
                SHIP,
            ],
        }
    )
    result = persona_node(deps)(_state("jester", _turn()))
    assert result["messages"][0].content == VOICED
    retry_prompt = deps.models["strong"].prompts[2]
    assert f"Your previous rewrite:\n{VOICED} Und wer noch?" in retry_prompt
    assert "The critic's notes:\nKeine eigene Frage." in retry_prompt


def test_three_rejected_rewrites_ship_the_plain_draft(make_deps):
    deps = make_deps(
        script={
            "persona": ["a", "b", "c"],
            "voice_critic": [
                Critique(verdict="retry", faults=["lost"], notes="x", score=1),
                Critique(verdict="retry", faults=["lost"], notes="y", score=1),
                Critique(verdict="retry", faults=["lost"], notes="z", score=1),
            ],
        }
    )
    result = persona_node(deps)(_state("jester", _turn()))
    assert result["messages"][0].content == DRAFT
    assert deps.models["strong"].calls == ["persona", "voice_critic"] * 3


def test_a_closing_line_rides_along_into_the_rewrite_and_the_critic(make_deps):
    deps = make_deps(script={"persona": VOICED + "\n\n" + CLOSING, "voice_critic": SHIP})
    turn = _turn().model_copy(update={"closing_line": CLOSING})
    result = persona_node(deps)(_state("jester", turn))
    assert result["messages"][0].content.endswith(CLOSING)
    assert f"The tutor's message:\n{DRAFT}\n\n{CLOSING}" in deps.models["strong"].prompts[0]
    assert f"The tutor's draft:\n{DRAFT}\n\n{CLOSING}" in deps.models["strong"].prompts[1]


def test_a_curated_turn_with_no_brief_gets_one_from_the_persona_node(make_deps):
    deps = make_deps(script={"persona": "<echo>", "voice_critic": SHIP})
    turn = TurnScratch(draft="Der Schritt.", closing_line=CLOSING)
    result = persona_node(deps)(_state("jester", turn))
    assert result["messages"][0].content == f"Der Schritt.\n\n{CLOSING}"
    assert "only the voice runs" in deps.models["strong"].prompts[0]
    assert "curated course text" in deps.models["strong"].prompts[0]
    assert deps.models["strong"].prompts[0].count("--- MESSAGE") == 1
    assert "Ist erlaubt." in deps.models["strong"].prompts[0]


def test_a_reaction_turn_is_the_characters_own_words_and_is_not_rewritten(make_deps):
    deps = make_deps(script={})
    turn = TurnScratch(draft="Arr, nicht mit mir.", guard=Guard.cheat, voiced=True)
    result = persona_node(deps)(_state("pirate", turn))
    assert result["messages"][0].content == "Arr, nicht mit mir."
    assert deps.models["strong"].calls == []


def test_a_case_turn_that_is_the_question_alone_is_not_rewritten(make_deps):
    deps = make_deps(script={})
    question = deps.question(QUESTION_ID)
    result = persona_node(deps)(_state("jester", _turn(draft=question.question)))
    assert result["messages"][0].content == question.question
    assert deps.models["strong"].calls == []


def test_what_the_character_says_after_the_question_joins_the_question_bubble(make_deps):
    voiced = "Ahoi?\n\nRichtig.\n\nArr, wer schreibt den Hinweis dazu?\n\nArr!\n\nJetzt du."
    deps = make_deps(script={"persona": voiced, "voice_critic": SHIP})
    turn = _turn(draft="Richtig.\n\nWer schreibt den Hinweis dazu?").model_copy(
        update={"input_hint": InputHint(kind="text", asks=True)}
    )
    result = persona_node(deps)(_state("pirate", turn))
    assert result["messages"][0].content == (
        "Ahoi?\n\nRichtig.\n\nArr, wer schreibt den Hinweis dazu?\nArr!\nJetzt du."
    )


def test_a_turn_that_asks_nothing_keeps_the_characters_closing_paragraph(make_deps):
    deps = make_deps(script={"persona": "Richtig?\n\nArr!", "voice_critic": SHIP})
    result = persona_node(deps)(_state("pirate", _turn(draft="Richtig.")))
    assert result["messages"][0].content == "Richtig?\n\nArr!"


def _check_in() -> TurnScratch:
    return TurnScratch(
        draft="Der Schritt.",
        closing_line=t("de", "clear_so_far"),
        input_hint=InputHint(kind="confirm", label=t("de", "clear_yes")),
    )


def test_a_check_in_the_character_signs_off_after_keeps_ja_weiter(make_deps):
    voiced = "Der Schritt, Landratte.\n\nKlar soweit? Arr, Leinen los!"
    deps = make_deps(script={"persona": voiced, "voice_critic": SHIP})
    result = persona_node(deps)(_state("pirate", _check_in()))
    yes = InputHint(kind="confirm", label=t("de", "clear_yes"))
    assert result["last_hint"] == yes
    assert result["turn"].input_hint == yes
    assert result["messages"][0].additional_kwargs["hint"] == yes.model_dump(mode="json")


def test_a_check_in_whose_message_lost_its_question_offers_weiter(make_deps):
    voiced = "Der Schritt, Rekrut.\n\nErst prüfen, dann melden. Weiter!"
    deps = make_deps(script={"persona": voiced, "voice_critic": SHIP})
    result = persona_node(deps)(_state("pirate", _check_in()))
    weiter = InputHint(kind="confirm", label=t("de", "continue_label"))
    assert result["last_hint"] == weiter
    assert result["turn"].input_hint == weiter
    assert result["messages"][0].additional_kwargs["hint"] == weiter.model_dump(mode="json")


def test_a_check_in_that_ends_on_its_question_keeps_ja_weiter(make_deps):
    voiced = "Der Schritt, Rekrut.\n\nKlar soweit?"
    deps = make_deps(script={"persona": voiced, "voice_critic": SHIP})
    result = persona_node(deps)(_state("pirate", _check_in()))
    assert result["last_hint"].label == t("de", "clear_yes")


def test_no_persona_ships_the_plain_text(make_deps):
    deps = make_deps(script={})
    result = persona_node(deps)(_state("", _turn()))
    assert result["messages"][0].content == DRAFT
    assert deps.models["strong"].calls == []


def test_the_clerk_gets_the_no_spice_line(make_deps):
    deps = make_deps(script={"persona": DRAFT, "voice_critic": SHIP})
    persona_node(deps)(_state("clerk", _turn()))
    assert "adds nothing of his own" in deps.models["strong"].prompts[0]


def test_the_mood_reaches_the_rewrite_prompt(make_deps):
    deps = make_deps(script={"persona": VOICED, "voice_critic": SHIP})
    state = _state("jester", _turn())
    state["mood"] = Mood.happy
    persona_node(deps)(state)
    assert "Tutor mood: happy" in deps.models["strong"].prompts[0]


def test_a_rewrite_that_still_genders_reaches_the_student_degendered(make_deps):
    deps = make_deps(script={"persona": "Die Mitarbeiter:innen prüfen das.", "voice_critic": SHIP})
    result = persona_node(deps)(_state("jester", _turn()))
    assert result["messages"][0].content == "Die Mitarbeiter prüfen das."


def test_plain_text_strips_the_markdown_the_bubble_cannot_render():
    assert plain_text("**Kurzantwort:** Ja") == "Kurzantwort: Ja"
    assert plain_text("### Was du beachten musst") == "Was du beachten musst"
    assert plain_text("__fett__ und *kursiv*") == "fett und kursiv"
    assert plain_text("* erste\n* zweite") == "- erste\n- zweite"
    assert plain_text("a\n\n---\n\nb") == "a\n\n\n\nb"


def test_plain_text_strips_the_asterisk_an_odd_emphasis_run_leaves_behind():
    assert plain_text("Nach den *Q&A 14* gilt das.") == ("Nach den Q&A der Kommission 14 gilt das.")
    assert (
        plain_text("Du darfst Lebensläufe sortieren, *wenn** dein Haus die Pflichten erfüllt.")
        == "Du darfst Lebensläufe sortieren, wenn dein Haus die Pflichten erfüllt."
    )
    assert plain_text("Der Gedankenstrich * bleibt.") == "Der Gedankenstrich * bleibt."


def test_plain_text_strips_a_node_marker_the_model_echoed_back():
    assert (
        plain_text("Arrr, der Betriebsrat sitzt mit am Tisch.\n\n[node:persona]")
        == "Arrr, der Betriebsrat sitzt mit am Tisch."
    )
    assert plain_text("[node:free_question] Das steht in Artikel 26.") == (
        "Das steht in Artikel 26."
    )


def test_plain_text_turns_the_spaces_the_bitmap_font_cannot_draw_into_ordinary_ones():
    assert plain_text("Das steht in Kapitel III, Abschnitt 2.") == (
        "Das steht in Kapitel III, Abschnitt 2."
    )
    assert plain_text("Kapitel IV und Anhang III.") == "Kapitel IV und Anhang III."


def test_plain_text_writes_every_citation_the_way_a_german_reader_does():
    assert plain_text("Art. 5(1)(f) und Annex III pt. 4(a)") == (
        "Art. 5 Abs. 1 Buchst. f und Anhang III Nr. 4 Buchst. a"
    )
    assert plain_text("**GDPR Art. 6(1)(f)** und Rec. 44") == (
        "Art. 6 Abs. 1 Buchst. f DSGVO und EG 44"
    )
    assert plain_text("BetrVG § 87(1) Nr. 6 gilt.") == "§ 87 Abs. 1 Nr. 6 BetrVG gilt."


def test_plain_text_renders_the_longest_citation_first():
    assert plain_text("Art. 5(1) und genauer Art. 5(1)(f)") == (
        "Art. 5 Abs. 1 und genauer Art. 5 Abs. 1 Buchst. f"
    )


def test_plain_text_leaves_option_letters_alone():
    assert plain_text("B) Der Chatassistent") == "B) Der Chatassistent"


def test_plain_text_degenders_the_output():
    assert plain_text("Nutzer*innen sehen das im Chat.") == "Nutzer sehen das im Chat."


def test_plain_text_writes_a_raw_act_id_as_the_act_name():
    assert plain_text("Nach ai_act Art. 96 gilt das.") == "Nach Art. 96 gilt das."
    assert plain_text("**gdpr Art. 5(1)** nennt das.") == "Art. 5 Abs. 1 DSGVO nennt das."
    assert plain_text("Siehe qa Q&A 6.") == "Siehe Q&A der Kommission 6."


def test_plain_text_joins_an_interjection_the_model_parked_at_a_line_end():
    said = plain_text("Der Assistent ist ein KI-System. Arr,  \nDein Haus ist der Betreiber.")
    assert said == "Der Assistent ist ein KI-System. Arr, Dein Haus ist der Betreiber."


def test_plain_text_keeps_the_break_between_two_paragraphs():
    assert plain_text("Das ist erlaubt,\n\nund das hier auch.") == (
        "Das ist erlaubt,\n\nund das hier auch."
    )


def test_plain_text_drops_an_interjection_left_at_a_paragraph_end():
    said = plain_text("Der Assistent ist ein KI-System. Arr,\n\nDein Haus ist der Betreiber.")
    assert said == "Der Assistent ist ein KI-System.\n\nDein Haus ist der Betreiber."


def test_plain_text_joins_a_single_line_break_inside_a_paragraph():
    assert plain_text("Das ist erlaubt. Tadaa!  \nVerlangt ist etwas anderes.") == (
        "Das ist erlaubt. Tadaa! Verlangt ist etwas anderes."
    )
    assert plain_text("Zwei Punkte:\n- erste\n- zweite") == "Zwei Punkte:\n- erste\n- zweite"


def test_plain_text_writes_a_non_breaking_hyphen_as_a_hyphen():
    assert plain_text("Ein KI‑System ist ein Werkzeug.") == "Ein KI-System ist ein Werkzeug."
