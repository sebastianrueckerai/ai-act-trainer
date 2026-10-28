from langchain_core.messages import HumanMessage

from app.graph.critic import Critique
from app.graph.events import settle_events, ui_events
from app.graph.grade import ProseChoice
from app.graph.state import (
    CitationPart,
    FilePart,
    InputHint,
    ModelAnswerCard,
    TurnScratch,
    UiEvent,
    initial_state,
)
from app.graph.triage import Triage
from app.i18n import t

# The first lesson turn from test_graph.py: triage's structured verdict and the
# persona rewrite, nothing else.
SHIP = Critique(verdict="ship", score=5)
SCRIPT = {
    "triage": Triage(guard="ok", intent="continue"),
    "persona": "<echo>",
    "critic": SHIP,
    "voice_critic": SHIP,
}


def _custom_events(graph, thread: str) -> list[dict]:
    config = {"configurable": {"thread_id": thread}}
    return list(
        graph.stream(
            initial_state("clerk") | {"messages": [HumanMessage("Hallo")]},
            config,
            stream_mode="custom",
        )
    )


def test_ui_events_project_the_turns_ui_events() -> None:
    scratch = TurnScratch(ui_events=[UiEvent(name="confetti", payload={"count": 1})])
    assert ui_events(scratch) == [
        {"type": "ui", "name": "confetti", "payload": {"count": 1}},
    ]


def test_settle_events_project_parts_and_hint() -> None:
    scratch = TurnScratch(
        parts=[
            ModelAnswerCard(
                question="q-01-01",
                model_answer="Ja.",
                explanation="Weil",
                citations=[
                    CitationPart(
                        ref="Art. 4(1)",
                        title="Art. 4",
                        quote="Zitat",
                        url="https://eur-lex.europa.eu/",
                    )
                ],
                correct=True,
            ),
            CitationPart(
                ref="Art. 4(1)",
                title="Art. 4",
                quote="Zitat",
                url="https://eur-lex.europa.eu/",
            ),
        ],
        input_hint=InputHint(kind="yes_no"),
    )
    # A part event carries what the page shows: the display form, German refs included.
    assert settle_events(scratch) == [
        {
            "type": "part",
            "out": {
                "kind": "card",
                "question": "q-01-01",
                "model_answer": "Ja.",
                "explanation": "Weil",
                "citations": [
                    {
                        "kind": "citations",
                        "ref": "Art. 4 Abs. 1",
                        "title": "Art. 4",
                        "quote": "Zitat",
                        "url": "https://eur-lex.europa.eu/",
                    }
                ],
                "correct": True,
                "tries": 1,
            },
        },
        {
            "type": "part",
            "out": {
                "kind": "citations",
                "ref": "Art. 4 Abs. 1",
                "title": "Art. 4",
                "quote": "Zitat",
                "url": "https://eur-lex.europa.eu/",
            },
        },
        {
            "type": "input_hint",
            "hint": {
                "kind": "yes_no",
                "choices": [],
                "label": None,
                "asks": False,
                "correct_key": None,
            },
        },
    ]


def test_settle_events_marks_file_parts() -> None:
    turn = TurnScratch(input_hint=InputHint(kind="text"))
    turn.parts.append(
        FilePart(
            url="/api/files/abc",
            title="Spickzettel: Der ganze Kurs",
            filename="spickzettel-kurs.pdf",
        )
    )

    events = settle_events(turn)

    file_events = [e for e in events if e["type"] == "part" and e["out"]["kind"] == "file"]
    assert len(file_events) == 1
    assert file_events[0]["out"] == {
        "kind": "file",
        "url": "/api/files/abc",
        "title": "Spickzettel: Der ganze Kurs",
        "filename": "spickzettel-kurs.pdf",
    }


def test_custom_stream_carries_turn_events(make_graph, content) -> None:
    graph = make_graph(script=SCRIPT)
    custom = _custom_events(graph, "events-custom")
    assert custom, "the first lesson step must publish its turn events"
    assert [event["out"]["ref"] for event in custom if event["type"] == "part"] == [
        "Art. 3 Nr. 1",
        "Art. 3 Nr. 4",
    ]
    assert [event["type"] for event in custom].count("input_hint") == 1
    # The step teaches first and checks in; its case waits behind the button (D96).
    assert custom[-1] == {
        "type": "input_hint",
        "hint": {
            "kind": "confirm",
            "choices": [],
            "label": t("de", "clear_yes"),
            "asks": False,
            "correct_key": None,
        },
    }


def test_the_check_in_opens_the_step_s_own_question(make_graph, content) -> None:
    script = {
        "triage": [Triage(guard="ok", intent="continue")] * 2,
        "persona": "<echo>",
        "critic": SHIP,
        "voice_critic": SHIP,
    }
    graph = make_graph(script=script)
    config = {"configurable": {"thread_id": "events-case"}}
    graph.invoke(initial_state("clerk") | {"messages": [HumanMessage("Hallo")]}, config)

    custom = list(
        graph.stream({"messages": [HumanMessage("Ja, weiter")]}, config, stream_mode="custom")
    )

    options = content.locales["de"].questions["q-01-11"].options
    correct = content.locales["de"].questions["q-01-11"].correct
    assert custom[-1] == {
        "type": "input_hint",
        "hint": {
            "kind": "choices",
            "choices": [{"key": option.key, "label": option.text} for option in options],
            "label": None,
            "asks": True,
            # A practice check-in names its own answer: the chip flashes on the click.
            "correct_key": correct,
        },
    }


def test_a_pending_choices_question_plus_help_produces_no_card_and_keeps_practice(
    make_graph, content
) -> None:
    script = {
        "triage": [
            Triage(guard="ok", intent="continue"),
            Triage(guard="ok", intent="continue"),
            Triage(guard="ok", intent="help"),
        ],
        "persona": "<echo>",
        "critic": SHIP,
        "voice_critic": SHIP,
        # A plea for help on a choice question is no attempt; the gate resolves the reply,
        # and once more the persona's rewrite of it.
        "prose": [ProseChoice(answer="none")] * 3,
        "reply": "Frag anders: was bedeutet ein KI-System im Sinne des Gesetzes?",
    }
    graph = make_graph(script=script)
    config = {"configurable": {"thread_id": "events-help-pending"}}
    graph.invoke(initial_state("clerk") | {"messages": [HumanMessage("Hallo")]}, config)
    graph.invoke({"messages": [HumanMessage("Ja, weiter")]}, config)

    custom = list(
        graph.stream(
            {"messages": [HumanMessage("Ich verstehe die Frage nicht.")]},
            config,
            stream_mode="custom",
        )
    )

    assert not [e for e in custom if e["type"] == "part" and e["out"]["kind"] == "card"]
    assert graph.get_state(config).values["practice"] is not None
    options = content.locales["de"].questions["q-01-11"].options
    correct = content.locales["de"].questions["q-01-11"].correct
    hint_events = [e for e in custom if e["type"] == "input_hint"]
    assert hint_events
    assert hint_events[-1] == {
        "type": "input_hint",
        "hint": {
            "kind": "choices",
            "choices": [{"key": option.key, "label": option.text} for option in options],
            "label": None,
            "asks": True,
            "correct_key": correct,
        },
    }


def test_custom_events_never_carry_a_test_answer(make_graph, content) -> None:
    graph = make_graph(script=SCRIPT)
    leaked = [str(chunk) for chunk in _custom_events(graph, "events-leak")]
    question = content.locales["de"].questions["q-01-01"]
    correct_text = next(
        (option.text for option in question.options if option.key == question.correct), ""
    )
    needle = question.model_answer or correct_text
    assert needle
    assert all(needle not in text for text in leaked)
