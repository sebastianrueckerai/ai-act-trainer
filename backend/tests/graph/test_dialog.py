from langchain_core.messages import HumanMessage, RemoveMessage

from app.graph.dialog import compact_node, help_node, react_node
from app.graph.state import Guard, InputHint, Mood, Phase, TurnScratch, initial_state
from app.i18n import t


def _long_history() -> list[HumanMessage]:
    return [HumanMessage(f"Nachricht {i} " + "x" * 800) for i in range(30)]


def test_compact_folds_old_messages_into_the_summary(make_deps):
    deps = make_deps(script={"compact": "Zusammenfassung der Unterhaltung."})
    state = initial_state("")
    state["messages"] = _long_history()
    result = compact_node(deps)(state)
    assert result["summary"] == "Zusammenfassung der Unterhaltung."
    assert [m.id for m in result["messages"]] == [f"m{i}" for i in range(22)]
    assert all(isinstance(m, RemoveMessage) for m in result["messages"])
    assert deps.models["fast"].calls == ["compact"]


def test_compact_appends_to_an_existing_summary(make_deps):
    deps = make_deps(script={"compact": "Zusammenfassung der Unterhaltung."})
    state = initial_state("")
    state["summary"] = "Bisher: Rollenwahl."
    state["messages"] = _long_history()
    result = compact_node(deps)(state)
    assert result["summary"] == "Bisher: Rollenwahl.\n\nZusammenfassung der Unterhaltung."


def test_compact_leaves_short_histories_alone(make_deps):
    deps = make_deps(script={})
    state = initial_state("")
    state["messages"] = [HumanMessage("kurz")]
    result = compact_node(deps)(state)
    assert result == {}
    assert deps.models["fast"].calls == []


def test_react_uses_the_persona_reaction_and_reasks(make_deps):
    deps = make_deps(script={})
    persona = next(iter(deps.content.personas.values()))
    state = initial_state(persona.id)
    state["phase"] = Phase.test
    state["pending_prompt"] = "Frage 3: War das erlaubt?"
    state["turn"] = TurnScratch(guard=Guard.cheat, guard_category=Guard.cheat)
    result = react_node(deps)(state)
    assert result["turn"].draft == f"{persona.reactions['cheat']}\n\nFrage 3: War das erlaubt?"
    assert result["mood"] == Mood.surprised
    assert result["turn"].guard_category == Guard.cheat


def test_react_without_a_persona_uses_the_neutral_locale_line(make_deps):
    deps = make_deps(script={})
    state = initial_state("")
    state["pending_prompt"] = "Sag »weiter«, wenn du bereit bist."
    state["turn"] = TurnScratch(guard=Guard.humor, guard_category=Guard.humor)
    result = react_node(deps)(state)
    assert result["turn"].draft == f"{t('de', 'react_humor')}\n\nSag »weiter«, wenn du bereit bist."
    assert result["mood"] == Mood.surprised


def test_help_answers_from_the_fast_model(make_deps):
    deps = make_deps(script={"help": "Du kannst »weiter« sagen oder eine Frage stellen."})
    state = initial_state("")
    state["phase"] = Phase.lesson
    state["pending_prompt"] = "Sag »weiter«."
    result = help_node(deps)(state)
    assert result["turn"].draft == "Du kannst »weiter« sagen oder eine Frage stellen."
    assert result["turn"].closing_line == "Sag »weiter«."
    assert deps.models["fast"].calls == ["help"]


def test_help_with_a_string_phase_still_answers(make_deps):
    deps = make_deps(script={"help": "Du kannst »weiter« sagen oder eine Frage stellen."})
    state = initial_state("")
    state["phase"] = "lesson"
    state["pending_prompt"] = "Sag »weiter«."
    result = help_node(deps)(state)
    assert result["turn"].draft == "Du kannst »weiter« sagen oder eine Frage stellen."


def test_react_on_an_ok_turn_with_a_persona_reasks_the_pending_prompt(make_deps):
    deps = make_deps(script={})
    persona = next(iter(deps.content.personas.values()))
    state = initial_state(persona.id)
    state["phase"] = Phase.done
    state["mood"] = Mood.happy
    state["pending_prompt"] = "Stell mir Fragen oder sage »start«, um den Test zu wiederholen."
    state["turn"] = TurnScratch(guard=Guard.ok)
    result = react_node(deps)(state)
    assert result["turn"].draft == "Stell mir Fragen oder sage »start«, um den Test zu wiederholen."
    assert result["turn"].guard_category is None
    assert "mood" not in result and state["mood"] is Mood.happy
    for line in persona.reactions.values():
        assert line not in result["turn"].draft
    assert deps.models["fast"].calls == []


def test_react_on_an_ok_turn_without_a_persona_reasks_the_pending_prompt(make_deps):
    deps = make_deps(script={})
    state = initial_state("")
    state["phase"] = Phase.test
    state["pending_prompt"] = "Frage 2: Was gilt in diesem Fall?"
    state["turn"] = TurnScratch()
    result = react_node(deps)(state)
    assert result["turn"].draft == "Frage 2: Was gilt in diesem Fall?"


def test_react_on_an_insult_sets_the_surprised_mood(make_deps):
    deps = make_deps(script={})
    persona = next(iter(deps.content.personas.values()))
    state = initial_state(persona.id)
    state["phase"] = Phase.test
    state["pending_prompt"] = "Frage 4: Wie lautet die richtige Antwort?"
    state["turn"] = TurnScratch(guard=Guard.insult, guard_category=Guard.insult)
    result = react_node(deps)(state)
    expected = f"{persona.reactions['insult']}\n\nFrage 4: Wie lautet die richtige Antwort?"
    assert result["turn"].draft == expected
    assert result["mood"] == Mood.surprised


def test_react_and_help_reasks_carry_the_last_structured_hint(make_deps):
    deps = make_deps(script={"help": "Sag »weiter« für den nächsten Schritt."})
    hint = InputHint(kind="yes_no")
    state = initial_state("")
    state["last_hint"] = hint
    state["pending_prompt"] = "Frage 2: War das erlaubt?"
    ok_turn = dict(state) | {"turn": TurnScratch(guard=Guard.ok)}
    assert react_node(deps)(ok_turn)["turn"].input_hint == hint
    guard_turn = dict(state) | {"turn": TurnScratch(guard=Guard.cheat, guard_category=Guard.cheat)}
    result = react_node(deps)(guard_turn)
    assert result["turn"].input_hint == hint
    assert result["turn"].draft == f"{t('de', 'react_cheat')}\n\nFrage 2: War das erlaubt?"
    help_state = dict(state) | {"phase": Phase.lesson}
    assert help_node(deps)(help_state)["turn"].input_hint == hint


def test_react_marks_a_persona_reaction_as_already_voiced(make_deps):
    deps = make_deps(script={})
    persona = next(iter(deps.content.personas.values()))
    state = initial_state(persona.id)
    state["pending_prompt"] = "Frage 3: War das erlaubt?"
    state["turn"] = TurnScratch(guard=Guard.cheat, guard_category=Guard.cheat)
    assert react_node(deps)(state)["turn"].voiced is True

    state["turn"] = TurnScratch(guard=Guard.ok)
    assert react_node(deps)(state)["turn"].voiced is False
