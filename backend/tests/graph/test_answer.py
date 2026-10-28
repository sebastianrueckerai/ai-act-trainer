from langchain_core.messages import HumanMessage

from app.graph.answer import free_question_node, free_question_prompt
from app.graph.brief import build_brief
from app.graph.critic import Critique
from app.graph.prompts import (
    ANSWER_IN_LOCALE,
    ANSWER_LENGTH_RULE,
    EXPERTISE_RULES,
    FREE_QUESTION,
)
from app.graph.state import InputHint, Phase, SessionState, TurnScratch, initial_state
from app.graph.tools import citations_from_text
from app.i18n import t

SHIP = Critique(verdict="ship", score=5)

CLOSING = "Stell mir weitere Fragen oder sage »start«."
FIVE_PARAGRAPHS = "\n\n".join(
    [
        "Allein anfangen darfst du damit nicht.",
        "Art. 26(7) nennt die Pflichten des Betreibers gegenüber den Beschäftigten.",
        "Betreiber ist dein Arbeitgeber, nicht du.",
        "Frag die Stelle, die bei euch über KI-Werkzeuge entscheidet.",
        "Bei einer Überwachung sitzt der Betriebsrat mit am Tisch.",
    ]
)
THREE_PARAGRAPHS = "\n\n".join(
    [
        "Allein anfangen darfst du damit nicht.",
        "Art. 26(7) nennt die Pflichten des Betreibers, und Betreiber ist dein Arbeitgeber.",
        "Frag die Stelle, die bei euch über KI-Werkzeuge entscheidet.",
    ]
)


def _free_state(message: str, turn: TurnScratch | None = None) -> SessionState:
    state = initial_state("")
    state["phase"] = Phase.free
    state["messages"] = [HumanMessage(message)]
    state["pending_prompt"] = CLOSING
    if turn is not None:
        state["turn"] = turn
    return state


def test_free_question_runs_the_tool_loop_and_cites_the_passage(make_deps):
    final_text = (
        "Nach Art. 26(7) gilt: Betreiber, die Arbeitgeber sind, müssen die Arbeitnehmer "
        "informieren."
    )
    deps = make_deps(
        script={
            "critic": SHIP,
            "free_question": [
                {"tool_calls": [{"name": "read_law", "args": {"citation": "Art. 26(7)"}}]},
                final_text,
            ],
        }
    )
    state = _free_state(
        "Muss ich als Arbeitgeber meine Mitarbeiter über die KI-Systeme informieren?"
    )
    result = free_question_node(deps)(state)
    turn = result["turn"]
    assert turn.draft == final_text
    assert [part.ref for part in turn.parts] == ["Art. 26(7)"]
    part = turn.parts[0]
    assert part.title == "Artikel 26: Pflichten der Betreiber von Hochrisiko-KI-Systemen"
    assert part.url == "https://eur-lex.europa.eu/eli/reg/2024/1689/2026-07-27/deu#art_26"
    assert part.quote.startswith(
        "Vor der Inbetriebnahme oder Verwendung eines Hochrisiko-KI-Systems am "
    )
    assert turn.closing_line == CLOSING
    assert turn.hedge_added is False
    assert deps.models["strong"].calls == ["free_question", "free_question", "critic"]


def test_free_question_appends_the_hedge_on_advice(make_deps):
    answer = "Ob Sie klagen können, hängt von den Umständen Ihres Falles ab."
    deps = make_deps(script={"critic": SHIP, "free_question": answer})
    state = _free_state("Kann ich meinen Arbeitgeber verklagen?", turn=TurnScratch(advice=True))
    result = free_question_node(deps)(state)
    assert result["turn"].draft == f"{answer}\n\n{t('de', 'hedge')}"
    assert result["turn"].hedge_added is True
    assert result["turn"].parts == []


def test_free_question_prompt_carries_the_expertise_rules(make_deps):
    deps = make_deps()
    brief = build_brief(deps, _free_state("Was gilt?"), "free_question")
    prompt = free_question_prompt(deps, brief)
    assert EXPERTISE_RULES.splitlines()[0] in prompt
    assert ANSWER_IN_LOCALE in prompt
    assert "- ai_act (KI-VO): " in prompt
    assert brief.text() in prompt
    assert prompt.startswith(FREE_QUESTION)


def test_free_question_prompt_closes_with_the_rules_and_the_length_line(make_deps):
    deps = make_deps()
    brief = build_brief(deps, _free_state("Was gilt?"), "free_question")
    prompt = free_question_prompt(deps, brief)
    assert prompt.endswith(f"{EXPERTISE_RULES}\n\n{ANSWER_LENGTH_RULE}")
    assert prompt.index(EXPERTISE_RULES) > prompt.index(brief.text())


def test_a_free_reask_without_a_pending_question_carries_the_last_hint(make_deps):
    hint = InputHint(kind="yes_no")
    deps = make_deps(script={"critic": SHIP, "free_question": "Art. 4(1) nennt die KI-Kompetenz."})
    state = _free_state("Was gilt für mich?", turn=TurnScratch())
    state["last_hint"] = hint
    assert free_question_node(deps)(state)["turn"].input_hint == hint


def test_the_reply_keeps_its_citations_as_parts_and_loses_them_in_the_prose(make_deps):
    reply = "Das ist erlaubt (Art. 4 Abs. 1).\n\nFundstellen: Art. 4 Abs. 1"
    deps = make_deps(script={"critic": SHIP, "free_question": reply})
    result = free_question_node(deps)(_free_state("Darf ich ein KI-Werkzeug ausprobieren?"))
    turn = result["turn"]
    assert [part.ref for part in turn.parts] == ["Art. 4(1)"]
    assert turn.draft == "Das ist erlaubt."


def test_citations_from_text_skips_a_citation_the_library_cannot_resolve(make_deps):
    deps = make_deps()
    parts = citations_from_text(deps, "Art. 143(1) ist entfallen, geblieben ist Art. 26(7).")
    assert [part.ref for part in parts] == ["Art. 26(7)"]
    assert parts[0].quote.startswith("Vor der Inbetriebnahme")


def test_free_question_past_the_chapters_still_answers(make_deps):
    answer = "Außerhalb der gebündelten Texte kann ich das nicht sagen."
    deps = make_deps(script={"critic": SHIP, "free_question": answer})
    state = _free_state("Was gilt in China?")
    state["chapter_idx"] = 1
    result = free_question_node(deps)(state)
    assert result["turn"].draft == answer
    assert deps.models["strong"].calls == ["free_question", "critic"]


def test_a_raw_act_id_in_the_answer_is_written_out_and_still_cited(make_deps):
    deps = make_deps(
        script={
            "critic": SHIP,
            "free_question": "Die Kommission kann nach ai_act Art. 96 Leitlinien geben.",
        }
    )
    result = free_question_node(deps)(_free_state("Was macht die Kommission?"))
    turn = result["turn"]
    assert turn.draft == "Die Kommission kann nach Art. 96 Leitlinien geben."
    assert [part.ref for part in turn.parts] == ["Art. 96"]


def test_an_answer_over_three_paragraphs_is_cut_to_the_conclusion_and_three(make_deps):
    deps = make_deps(
        script={"critic": SHIP, "free_question": FIVE_PARAGRAPHS, "shorten": THREE_PARAGRAPHS}
    )
    result = free_question_node(deps)(_free_state("Darf ich Bewerbungen sortieren lassen?"))
    assert result["turn"].draft == THREE_PARAGRAPHS
    assert [part.ref for part in result["turn"].parts] == ["Art. 26(7)"]
    assert deps.models["strong"].calls == ["free_question", "shorten", "critic"]


def test_an_answer_of_three_paragraphs_is_left_alone(make_deps):
    deps = make_deps(script={"critic": SHIP, "free_question": THREE_PARAGRAPHS})
    result = free_question_node(deps)(_free_state("Darf ich Bewerbungen sortieren lassen?"))
    assert result["turn"].draft == THREE_PARAGRAPHS
    assert deps.models["strong"].calls == ["free_question", "critic"]


def test_a_shortened_answer_that_lost_a_citation_is_thrown_away(make_deps):
    without = THREE_PARAGRAPHS.replace("Art. 26(7)", "Die Verordnung")
    deps = make_deps(script={"critic": SHIP, "free_question": FIVE_PARAGRAPHS, "shorten": without})
    result = free_question_node(deps)(_free_state("Darf ich Bewerbungen sortieren lassen?"))
    assert result["turn"].draft == FIVE_PARAGRAPHS
    assert deps.models["strong"].calls == ["free_question", "shorten", "critic"]


def test_an_empty_shortening_is_thrown_away(make_deps):
    deps = make_deps(script={"critic": SHIP, "free_question": FIVE_PARAGRAPHS, "shorten": "  "})
    result = free_question_node(deps)(_free_state("Darf ich Bewerbungen sortieren lassen?"))
    assert result["turn"].draft == FIVE_PARAGRAPHS


def test_the_expertise_rules_answer_the_employee_not_the_deployer(make_deps):
    deps = make_deps()
    brief = build_brief(deps, _free_state("Was gilt?"), "free_question")
    prompt = free_question_prompt(deps, brief)
    assert "whether they may do it on their own, who in the company decides" in prompt
    assert "an employee may not start a high-risk use on their own initiative" in prompt


def test_a_free_answer_the_critic_rejects_is_written_again_with_the_notes(make_deps):
    deps = make_deps(
        script={
            "free_question": ["zu lang und falsch", "Kurz: ja, wenn ein Mensch prüft."],
            "critic": [
                Critique(verdict="retry", faults=["unhelpful"], notes="Kürzer.", score=2),
                SHIP,
            ],
        }
    )
    result = free_question_node(deps)(_free_state("Darf ich Mails mit KI schreiben?"))
    assert result["turn"].draft == "Kurz: ja, wenn ein Mensch prüft."
    assert "--- YOUR LAST DRAFT\nzu lang und falsch" in deps.models["strong"].prompts[2]
    assert "Fault: unhelpful" in deps.models["strong"].prompts[2]
    assert "Notes: Kürzer." in deps.models["strong"].prompts[2]
    assert "only the voice runs" not in result["turn"].brief
    assert "no question of the course open" in result["turn"].brief
