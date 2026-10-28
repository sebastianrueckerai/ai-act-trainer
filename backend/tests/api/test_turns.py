import asyncio
import json
import time
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, RemoveMessage
from sqlalchemy import select

from app.api.chat_events import TokenEvent, format_sse
from app.content.citations import de_ref
from app.graph.critic import Critique
from app.graph.grade import Verdict
from app.graph.state import InputHint, Phase
from app.graph.state import TestState as RunningTest
from app.graph.triage import Triage
from app.storage.models import TrainingSession

# The persona echoes the draft and the critics ship it, so the streamed text is the
# tutor draft itself: one expectation, no model wording.
SHIP = Critique(verdict="ship", score=5)
LESSON_SCRIPT = {
    "triage": Triage(guard="ok", intent="continue"),
    "persona": "<echo>",
    "critic": SHIP,
    "voice_critic": SHIP,
}
PRACTICE_REPLY = "Genau, das darfst du."
OPENING_SCRIPT = {"persona": "<echo>", "critic": SHIP, "voice_critic": SHIP}

# Every step of chapter one ends on its own question (D76), so walking from one step
# to the next means answering it first.
STEP_WALK_SCRIPT = {
    "triage": [
        Triage(guard="ok", intent="continue"),
        Triage(guard="ok", intent="continue"),
        Triage(guard="ok", intent="answer"),
        Triage(guard="ok", intent="continue"),
    ],
    "reply": PRACTICE_REPLY,
    "persona": "<echo>",
    "critic": SHIP,
    "voice_critic": SHIP,
}
VERDICT_WALK_SCRIPT = {
    "triage": [
        Triage(guard="ok", intent="continue"),
        Triage(guard="ok", intent="continue"),
        Triage(guard="ok", intent="answer"),
    ],
    "reply": PRACTICE_REPLY,
    "persona": "<echo>",
    "critic": SHIP,
    "voice_critic": SHIP,
}
ANSWER_THEN_STEP_SCRIPT = {
    "triage": [
        Triage(guard="ok", intent="continue"),
        Triage(guard="ok", intent="answer"),
        Triage(guard="ok", intent="continue"),
    ],
    "reply": PRACTICE_REPLY,
    "persona": "<echo>",
    "critic": SHIP,
    "voice_critic": SHIP,
}
CONTINUE_SETUP_SCRIPT = {
    "triage": [Triage(guard="ok", intent="start_test"), Triage(guard="ok", intent="continue")],
    "persona": "<echo>",
    "critic": SHIP,
    "voice_critic": SHIP,
}

# The first lesson turn's citations (Art. 3 Nr. 1, Art. 3 Nr. 4) never reach the model;
# the three option labels of the question its step asks are the only fields translate_fields
# must reply to.
ENGLISH_CHOICES = [
    "Nothing new, a spell checker is not an AI system.",
    "It is an AI system, and your company is its deployer.",
    "It is an AI system, and its maker is its deployer.",
]
ENGLISH_TITLES = "\n".join(f"{i}: Chapter {i}" for i in range(1, 9))
ENGLISH_LESSON_SCRIPT = {
    "triage": Triage(guard="ok", intent="continue"),
    "persona": "<echo>",
    "critic": SHIP,
    "voice_critic": SHIP,
    "translate": "This chapter shows you what you may do with AI.",
    # The chapter titles render once per process, before the first turn's fields.
    "translate_fields": [
        ENGLISH_TITLES,
        "\n".join(f"{i}: {label}" for i, label in enumerate(ENGLISH_CHOICES, 1)),
        "\n".join(f"{i}: {label}" for i, label in enumerate(ENGLISH_CHOICES, 1)),
    ],
}

DEFAULT_TURNS_SCRIPT = {
    "triage": Triage(guard="ok", intent="continue"),
    "persona": "<echo>",
    "critic": SHIP,
    "voice_critic": SHIP,
}

# The critic sends every rewrite back and the turn falls back to the draft: whatever
# streamed on the way must still be the text the student ends up reading.
FAILED_REWRITE_SCRIPT = {
    "triage": Triage(guard="ok", intent="continue"),
    "persona": "Ein erster Versuch.",
    "critic": SHIP,
    "voice_critic": Critique(verdict="retry", faults=["lost"], score=1),
}

GRADE_SCRIPT = {
    "triage": Triage(guard="ok", intent="answer"),
    "grade": Verdict(correct=True),
    "persona": "<echo>",
    "critic": SHIP,
    "voice_critic": SHIP,
}

TEST_HINT_SCRIPT = {
    "triage": Triage(guard="ok", intent="answer"),
    "persona": "<echo>",
    "critic": SHIP,
    "voice_critic": SHIP,
}

BROKEN_SCRIPT = {"persona": "<echo>", "critic": SHIP, "voice_critic": SHIP}

CORRECT_FREE_TEXT_ANSWER = (
    "Erlaubt ist das Entwerfen mit dem KI-System, und statt einer Genehmigung "
    "braucht es KI-Kompetenz und das Prüfen des Ergebnisses."
)


def _run(coro):
    return asyncio.run(coro)


def _thread_id(client, session_id: int) -> str:
    with client.app.state.session_factory() as db:
        training_session = db.scalar(
            select(TrainingSession).where(TrainingSession.id == session_id)
        )
    assert training_session is not None
    return training_session.thread_id


def _stream(client, url: str, body: dict | None = None):
    with client.stream("POST", url, json=body) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-cache"
        lines = list(response.iter_lines())
    events = [json.loads(line[6:]) for line in lines if line.startswith("data: ")]
    framed = [line[7:] for line in lines if line.startswith("event: ")]
    return events, framed


def _stream_turns(client, session_id: int, text: str):
    return _stream(client, f"/api/chat/{session_id}/turns", {"text": text})


def _start(client, persona_id: str = "clerk", display_locale: str = "de") -> int:
    client.post("/api/auth/dev/login", json={"subject": "anna"})
    body = {"persona_id": persona_id, "display_locale": display_locale}
    return client.post("/api/session", json=body).json()["id"]


def _first_chapter(client):
    return next(iter(client.app.state.content.locales["de"].chapters.values()))


@pytest.mark.parametrize("scripted_client", [LESSON_SCRIPT], indirect=True)
def test_a_lesson_turn_streams_the_event_sequence(scripted_client) -> None:
    session_id = _start(scripted_client)

    taught, _ = _stream_turns(scripted_client, session_id, "weiter")
    assert _first_chapter(scripted_client).steps[0].text in taught[-1]["text"]
    events, framed = _stream_turns(scripted_client, session_id, "Ja, weiter")

    names = [event["event"] for event in events]
    assert set(names) <= {
        "status",
        "working",
        "token",
        "ui",
        "part",
        "input_hint",
        "message",
        "error",
    }
    assert events[0] == {"event": "status", "node": "begin"}
    # The page learns which step runs, in the character's words, as each one starts. A
    # lesson step is curated text: reading the student's message is the one step here.
    working = [event for event in events if event["event"] == "working"]
    assert [event["step"] for event in working] == ["reading"]
    clerk = scripted_client.app.state.content.personas["clerk"]
    assert working[0]["text"] in clerk.working["reading"]
    # every data frame is announced by an event: line carrying the same name
    assert framed == names
    assert "triage" in {event["node"] for event in events if event["event"] == "status"}
    assert names[-1] == "message"
    hint_events = [event for event in events if event["event"] == "input_hint"]
    assert len(hint_events) == 1
    assert hint_events[0]["hint"]["kind"] == "choices"
    message = events[-1]
    assert message["hint"]["kind"] == "choices"
    # statuses are a pure node-name whitelist: no state delta ever leaves the graph
    assert all(set(event) == {"event", "node"} for event in events if event["event"] == "status")
    # tokens: the settled text, whole and final. The case turn carries only the
    # protected question, which never reaches the rewrite, so the teaching turn is
    # the one that streams.
    taught_tokens = "".join(event["text"] for event in taught if event["event"] == "token")
    assert taught_tokens == taught[-1]["text"]


@pytest.mark.parametrize("scripted_client", [ENGLISH_LESSON_SCRIPT], indirect=True)
def test_an_english_session_streams_the_translation_not_the_german_draft(
    scripted_client,
) -> None:
    session_id = _start(scripted_client, display_locale="en")

    taught, _ = _stream_turns(scripted_client, session_id, "weiter")
    # the English citation form, not de_ref'd back into German
    assert [part["ref"] for part in taught[-1]["parts"]] == ["Art. 3(1)", "Art. 3(4)"]
    events, _ = _stream_turns(scripted_client, session_id, "Ja, weiter")

    tokens = "".join(event["text"] for event in events if event["event"] == "token")
    # only the translate node's reply call is a token: no German persona chunk, and
    # no leak of translate_fields' raw untranslated numbered list into the stream.
    assert tokens == "This chapter shows you what you may do with AI."
    message = events[-1]
    assert message["event"] == "message"
    assert message["text"] == "This chapter shows you what you may do with AI."
    assert [choice["label"] for choice in message["hint"]["choices"]] == ENGLISH_CHOICES
    # What streamed is what settled, English refs included.
    part_events = [event for event in taught if event["event"] == "part"]
    assert [event["part"]["ref"] for event in part_events] == [
        part["ref"] for part in taught[-1]["parts"]
    ]
    # The chapter line follows the flag, in the turn's stage event and in the session,
    # rendered once for the whole process.
    stage_events = [e for e in taught if e["event"] == "ui" and e["name"] == "stage"]
    assert stage_events[0]["payload"]["chapters"][0]["title"] == "Chapter 1"
    session = scripted_client.get("/api/session").json()
    assert session["stage"]["chapters"][0]["title"] == "Chapter 1"
    chapters = scripted_client.app.state.content.locales["de"].chapters
    first_title = sorted(chapters.values(), key=lambda c: c.id)[0].title
    fast = scripted_client.app.state.deps.models["fast"]
    assert sum(first_title in p for p in fast.prompts if "[node:translate_fields]" in p) == 1


@pytest.mark.parametrize("scripted_client", [OPENING_SCRIPT], indirect=True)
def test_the_opening_greets_before_the_lesson_streams(scripted_client) -> None:
    session_id = _start(scripted_client)

    events, _ = _stream(scripted_client, f"/api/chat/{session_id}/opening")

    # The canned greeting is the first token, out before any node ran.
    tokens = [event for event in events if event["event"] == "token"]
    greeting = tokens[0]["text"] if tokens else ""
    persona_openings = scripted_client.app.state.content.personas["clerk"].openings
    assert any(greeting.startswith(line[:20]) for line in persona_openings)
    message = events[-1]
    assert message["event"] == "message"
    assert message["text"].startswith(greeting.strip())
    assert "Ein KI-System ist ein Werkzeug" in message["text"]


@pytest.mark.parametrize(
    "scripted_client",
    [
        {
            **OPENING_SCRIPT,
            "translate": ["Good day, the queue ends here.", "The lesson."],
            "translate_fields": "1: Article 3\n2: Article 3",
        }
    ],
    indirect=True,
)
def test_the_english_opening_greets_in_english_first_and_stores_it_once(scripted_client) -> None:
    session_id = _start(scripted_client, display_locale="en")

    events, _ = _stream(scripted_client, f"/api/chat/{session_id}/opening")

    tokens = [event["text"] for event in events if event["event"] == "token"]
    assert tokens[0] == "Good day, the queue ends here.\n\n"
    assert tokens[1] == "The lesson."
    assert events[-1]["text"] == "Good day, the queue ends here.\n\nThe lesson."
    fast = scripted_client.app.state.deps.models["fast"]
    # The greeting went to the model once, on its own; the body once, without it.
    greeting = scripted_client.app.state.content.personas["clerk"].openings
    seen = [p for p in fast.prompts if any(line[:20] in p for line in greeting)]
    assert len(seen) == 1


@pytest.mark.parametrize("scripted_client", [OPENING_SCRIPT], indirect=True)
def test_the_greeting_waits_a_beat_before_it_lands(scripted_client) -> None:
    session_id = _start(scripted_client)

    # A greeting that arrives at the first millisecond reads as a system message,
    # not a character speaking: the typing indicator gets its beat first, and the
    # greeting is the stream's first frame, so the whole stream cannot beat it.
    started = time.monotonic()
    events, _ = _stream(scripted_client, f"/api/chat/{session_id}/opening")
    assert events[0]["event"] == "token"
    elapsed = time.monotonic() - started
    assert elapsed >= 0.6
    assert elapsed < 5


def _settled_english(client) -> list[dict]:
    """The assistant messages once the background rendering has landed on all of them."""
    for _ in range(100):
        messages = client.get("/api/session").json()["messages"]
        english = [m for m in messages if m["role"] == "assistant"]
        if not any(m["translating"] for m in english):
            return english
        time.sleep(0.05)
    raise AssertionError("the rendering never settled")


@pytest.mark.parametrize("scripted_client", [DEFAULT_TURNS_SCRIPT], indirect=True)
def test_the_flag_flip_renders_the_whole_history_once(scripted_client) -> None:
    session_id = _start(scripted_client)
    _stream_turns(scripted_client, session_id, "weiter")
    _stream_turns(scripted_client, session_id, "Ja, weiter")  # ends on a choices question
    fast = scripted_client.app.state.deps.models["fast"]
    fast.script["translate"] = "Everything is allowed, with a check."
    fast.script["translate_fields"] = "\n".join(f"{i}: Option {i}" for i in range(1, 10))

    flipped = scripted_client.put(
        f"/api/session/{session_id}/display-locale", json={"display_locale": "en"}
    )
    assert flipped.status_code == 200
    assert flipped.json()["display_locale"] == "en"
    # The flip answers at once: the German still shows, marked as on its way.
    pending = [m for m in flipped.json()["messages"] if m["role"] == "assistant"]
    assert pending and all(m["translating"] for m in pending)
    assert all(m["text"] != "Everything is allowed, with a check." for m in pending)
    assert all(m["hint"] is not None for m in pending)
    assert not any(m["translating"] for m in flipped.json()["messages"] if m["role"] == "user")

    english = _settled_english(scripted_client)
    assert [m["text"] for m in english] == ["Everything is allowed, with a check."] * len(english)
    session = scripted_client.get("/api/session").json()
    assert session["hint"]["kind"] == "choices"
    assert [c["label"] for c in session["hint"]["choices"]] == ["Option 1", "Option 2", "Option 3"]
    assert english[-1]["hint"] == session["hint"]

    # The second flip renders nothing anew; the German comes back intact, at once.
    calls = len(fast.prompts)
    back = scripted_client.put(
        f"/api/session/{session_id}/display-locale", json={"display_locale": "de"}
    ).json()
    assert [c["label"] for c in back["hint"]["choices"]] != ["Option 1", "Option 2", "Option 3"]
    assert all(m["text"] != "" and not m["translating"] for m in back["messages"])
    again = scripted_client.put(
        f"/api/session/{session_id}/display-locale", json={"display_locale": "en"}
    ).json()
    assert [c["label"] for c in again["hint"]["choices"]] == ["Option 1", "Option 2", "Option 3"]
    assert [m["text"] for m in again["messages"] if m["role"] == "assistant"] == [
        "Everything is allowed, with a check."
    ] * len(english)
    assert not any(m["translating"] for m in again["messages"])
    assert len(fast.prompts) == calls


def test_a_message_stored_without_a_hint_or_rendering_is_still_served(scripted_client) -> None:
    session_id = _start(scripted_client)
    _stream_turns(scripted_client, session_id, "weiter")
    config = {"configurable": {"thread_id": _thread_id(scripted_client, session_id)}}
    graph = scripted_client.app.state.graph
    # The shape a message had before hints and renderings were stored on it.
    old = AIMessage("Alt.", additional_kwargs={"parts": [], "en_text": "Old."})
    _run(graph.aupdate_state(config, {"messages": [old]}, as_node="persona"))
    fast = scripted_client.app.state.deps.models["fast"]
    fast.script["translate"] = "Rendered."
    fast.script["translate_fields"] = "1: One\n2: Two"
    scripted_client.put(f"/api/session/{session_id}/display-locale", json={"display_locale": "en"})

    body = scripted_client.get("/api/session").json()
    assert body["messages"][-1]["text"] in ("Alt.", "Rendered.")
    assert body["messages"][-1]["hint"] is None
    assert body["hint"]["kind"] in ("text", "confirm", "choices", "yes_no")
    english = _settled_english(scripted_client)
    assert english[-1]["text"] == "Rendered."


def test_three_quick_flips_end_on_the_last_one_and_render_once(scripted_client) -> None:
    session_id = _start(scripted_client)
    _stream_turns(scripted_client, session_id, "weiter")
    fast = scripted_client.app.state.deps.models["fast"]
    fast.script["translate"] = "Once."
    fast.script["translate_fields"] = "1: One\n2: Two"

    for locale in ("en", "de", "en"):
        answer = scripted_client.put(
            f"/api/session/{session_id}/display-locale", json={"display_locale": locale}
        )
        assert answer.status_code == 200
        assert answer.json()["display_locale"] == locale

    english = _settled_english(scripted_client)
    assert [m["text"] for m in english] == ["Once."] * len(english)
    assert fast.calls.count("translate") == len(english)


def test_a_failed_rendering_serves_the_german_unmarked_until_the_next_flip(
    scripted_client,
) -> None:
    session_id = _start(scripted_client)
    _stream_turns(scripted_client, session_id, "weiter")
    fast = scripted_client.app.state.deps.models["fast"]
    fast.script["translate"] = [RuntimeError("proxy down"), "Fine now."]
    fast.script["translate_fields"] = "1: One\n2: Two"

    scripted_client.put(f"/api/session/{session_id}/display-locale", json={"display_locale": "en"})
    # The round fails: the German shows, readable, and a session read starts nothing anew.
    for _ in range(40):
        time.sleep(0.05)
        body = scripted_client.get("/api/session").json()
        if not any(m["translating"] for m in body["messages"]):
            break
    calls = fast.calls.count("translate")
    assert calls == 1
    last = [m for m in body["messages"] if m["role"] == "assistant"][-1]
    assert "Ein KI-System" in last["text"] and not last["translating"]
    scripted_client.get("/api/session")
    assert fast.calls.count("translate") == 1
    # The next flip is a fresh try.
    scripted_client.put(f"/api/session/{session_id}/display-locale", json={"display_locale": "de"})
    scripted_client.put(f"/api/session/{session_id}/display-locale", json={"display_locale": "en"})
    english = _settled_english(scripted_client)
    assert english[-1]["text"] == "Fine now."


def test_messages_carry_their_ids_in_the_session_and_the_closing_event(scripted_client) -> None:
    session_id = _start(scripted_client)
    events, _ = _stream_turns(scripted_client, session_id, "weiter")

    body = scripted_client.get("/api/session").json()
    config = {"configurable": {"thread_id": _thread_id(scripted_client, session_id)}}
    stored = _run(scripted_client.app.state.graph.aget_state(config)).values["messages"]
    assert [m["id"] for m in body["messages"]] == [m.id for m in stored]
    assert events[-1]["id"] == stored[-1].id
    assert events[-1]["translating"] is False


def test_the_history_job_never_brings_back_a_message_compaction_removed(scripted_client) -> None:
    from app.api import chat as chat_module

    session_id = _start(scripted_client)
    _stream_turns(scripted_client, session_id, "weiter")
    _stream_turns(scripted_client, session_id, "Ja, weiter")
    config = {"configurable": {"thread_id": _thread_id(scripted_client, session_id)}}
    graph = scripted_client.app.state.graph
    before = _run(graph.aget_state(config)).values["messages"]
    oldest = next(m for m in before if isinstance(m, AIMessage))
    real = chat_module.render_en

    def render_after_compaction(model, text, parts, hint):
        # Compaction runs between the job's snapshot and its write.
        _run(
            graph.aupdate_state(
                config, {"messages": [RemoveMessage(id=oldest.id)]}, as_node="compact"
            )
        )
        return real(model, text, parts, hint)

    fast = scripted_client.app.state.deps.models["fast"]
    fast.script["translate"] = "Rendered."
    fast.script["translate_fields"] = "1: One\n2: Two\n3: Three"
    with patch.object(chat_module, "render_en", render_after_compaction):
        scripted_client.put(
            f"/api/session/{session_id}/display-locale", json={"display_locale": "en"}
        )
        _settled_english(scripted_client)

    after = _run(graph.aget_state(config)).values["messages"]
    assert oldest.id not in [m.id for m in after]
    assert len(after) == len(before) - 1


def test_a_failed_chapter_title_rendering_leaves_the_titles_german(scripted_client) -> None:
    scripted_client.app.state.deps.models["fast"].script["translate_fields"] = RuntimeError("down")
    session_id = _start(scripted_client, display_locale="en")

    body = scripted_client.get("/api/session").json()

    assert body["id"] == session_id
    chapters = scripted_client.app.state.content.locales["de"].chapters
    first_title = sorted(chapters.values(), key=lambda c: c.id)[0].title
    assert body["stage"]["chapters"][0]["title"] == first_title


@pytest.mark.parametrize(
    "scripted_client",
    [
        {
            **OPENING_SCRIPT,
            "translate": [RuntimeError("down"), "The lesson, greeting included."],
            "translate_fields": "1: Article 3\n2: Article 3",
        }
    ],
    indirect=True,
)
def test_a_failed_greeting_rendering_greets_in_german_and_the_turn_goes_on(
    scripted_client,
) -> None:
    session_id = _start(scripted_client, display_locale="en")

    events, _ = _stream(scripted_client, f"/api/chat/{session_id}/opening")

    tokens = [event["text"] for event in events if event["event"] == "token"]
    persona_openings = scripted_client.app.state.content.personas["clerk"].openings
    assert any(tokens[0].startswith(line[:20]) for line in persona_openings)
    assert not [event for event in events if event["event"] == "error"]
    assert events[-1]["text"] == "The lesson, greeting included."


@pytest.mark.parametrize("scripted_client", [DEFAULT_TURNS_SCRIPT], indirect=True)
def test_a_turn_closes_at_the_daily_student_cap_without_calling_the_model(scripted_client) -> None:
    session_id = _start(scripted_client)
    scripted_client.app.state.settings.turn_limit_user_day = 2

    for _ in range(2):
        events, _ = _stream_turns(scripted_client, session_id, "weiter")
        assert events[-1]["event"] == "message"

    calls = len(scripted_client.app.state.deps.models["fast"].prompts)
    third, _ = _stream_turns(scripted_client, session_id, "weiter")
    assert [event["event"] for event in third] == ["error"]
    assert third[0]["code"] == "limit"
    assert third[0]["message"] == "chat.limit"
    # the refused turn never reaches a model
    assert len(scripted_client.app.state.deps.models["fast"].prompts) == calls


@pytest.mark.parametrize("scripted_client", [DEFAULT_TURNS_SCRIPT], indirect=True)
def test_the_global_cap_stops_a_second_student_once_the_day_is_full(scripted_client) -> None:
    scripted_client.app.state.settings.turn_limit_global_day = 1
    scripted_client.app.state.settings.turn_limit_user_day = 50

    anna = _start(scripted_client)
    events, _ = _stream_turns(scripted_client, anna, "weiter")
    assert events[-1]["event"] == "message"

    scripted_client.post("/api/auth/dev/login", json={"subject": "bernd"})
    bernd = scripted_client.post(
        "/api/session", json={"persona_id": "clerk", "display_locale": "de"}
    ).json()["id"]
    refused, _ = _stream_turns(scripted_client, bernd, "weiter")
    assert refused[0]["event"] == "error" and refused[0]["code"] == "limit"


@pytest.mark.parametrize("scripted_client", [OPENING_SCRIPT], indirect=True)
def test_the_opening_streams_the_first_lesson_step_and_adds_no_student_message(
    scripted_client,
) -> None:
    session_id = _start(scripted_client)

    events, framed = _stream(scripted_client, f"/api/chat/{session_id}/opening")

    names = [event["event"] for event in events]
    assert framed == names
    assert names[-1] == "message"
    nodes = {event["node"] for event in events if event["event"] == "status"}
    # the opening enters below triage: no student text exists to triage
    assert "triage" not in nodes
    assert {"lesson_step", "persona"} <= nodes
    assert _first_chapter(scripted_client).steps[0].text in events[-1]["text"]
    messages = scripted_client.get("/api/session").json()["messages"]
    assert [message["role"] for message in messages] == ["assistant"]


@pytest.mark.parametrize("scripted_client", [OPENING_SCRIPT], indirect=True)
def test_a_second_opening_is_refused(scripted_client) -> None:
    session_id = _start(scripted_client)
    _stream(scripted_client, f"/api/chat/{session_id}/opening")

    response = scripted_client.post(f"/api/chat/{session_id}/opening")

    assert response.status_code == 409


@pytest.mark.parametrize("scripted_client", [CONTINUE_SETUP_SCRIPT], indirect=True)
def test_continue_reaches_the_lesson_with_no_student_message_and_no_triage_call(
    scripted_client,
) -> None:
    session_id = _start(scripted_client)
    _stream(scripted_client, f"/api/chat/{session_id}/opening")
    # The residual confirm hint a /continue click still needs: a declined test leaves the
    # student on the step they were on, with its question still open (D89).
    _stream_turns(scripted_client, session_id, "Ich will den Test machen.")
    _stream_turns(scripted_client, session_id, "no")

    events, framed = _stream(scripted_client, f"/api/chat/{session_id}/continue")

    names = [event["event"] for event in events]
    assert framed == names
    nodes = {event["node"] for event in events if event["event"] == "status"}
    assert "triage" not in nodes
    assert {"lesson_step", "persona"} <= nodes
    assert names[-1] == "message"
    questions = scripted_client.app.state.content.locales["de"].questions
    still_open = questions[_first_chapter(scripted_client).steps[0].question]
    assert still_open.question in events[-1]["text"]

    messages = scripted_client.get("/api/session").json()["messages"]
    assert [m["role"] for m in messages] == [
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
        "assistant",
    ]


def _wait_at_chapter_end(client, session_id: int, chapter_idx: int, label: str) -> list:
    """The thread as a chapter end leaves it: the chapter done, its button waiting."""
    chapters = sorted(client.app.state.content.locales["de"].chapters.values(), key=lambda c: c.id)
    last = chapter_idx + 1 == len(chapters)
    config = {"configurable": {"thread_id": _thread_id(client, session_id)}}
    seed = {
        "phase": Phase.free if last else Phase.lesson,
        "chapter_idx": chapter_idx,
        "step_idx": len(chapters[chapter_idx].steps),
        "chapters_done": [chapter.id for chapter in chapters[: chapter_idx + 1]],
        "pending_case": None,
        "last_hint": InputHint(kind="confirm", label=label),
    }
    _run(client.app.state.graph.aupdate_state(config, seed, as_node="translate"))
    return chapters


@pytest.mark.parametrize("scripted_client", [OPENING_SCRIPT], indirect=True)
def test_the_button_after_a_chapter_end_opens_the_next_chapter_on_its_level_card(
    scripted_client,
) -> None:
    session_id = _start(scripted_client)
    _stream(scripted_client, f"/api/chat/{session_id}/opening")
    chapters = _wait_at_chapter_end(scripted_client, session_id, 0, "Weiter zu Kapitel 2")

    events, _ = _stream(scripted_client, f"/api/chat/{session_id}/continue")

    level = {"kind": "chapter_start", "title": "Was du hineingeben darfst"}
    parts = [event["part"] for event in events if event["event"] == "part"]
    assert parts[0] == level | {"intro": chapters[1].intro}
    assert events[-1]["parts"][0] == parts[0]
    assert chapters[1].steps[0].text in events[-1]["text"]
    stage = next(e["payload"] for e in events if e["event"] == "ui" and e["name"] == "stage")
    assert [chapter["state"] for chapter in stage["chapters"][:3]] == ["done", "current", "locked"]


@pytest.mark.parametrize("scripted_client", [OPENING_SCRIPT], indirect=True)
def test_the_button_after_the_last_chapter_starts_the_test_in_one_click(scripted_client) -> None:
    session_id = _start(scripted_client)
    _stream(scripted_client, f"/api/chat/{session_id}/opening")
    _wait_at_chapter_end(scripted_client, session_id, 7, "Zum Test")

    events, _ = _stream(scripted_client, f"/api/chat/{session_id}/continue")

    names = [event["name"] for event in events if event["event"] == "ui"]
    assert "test_started" in names
    assert scripted_client.get("/api/session").json()["phase"] == "test"


def test_continue_before_the_session_is_opened_is_refused(scripted_client) -> None:
    session_id = _start(scripted_client)

    response = scripted_client.post(f"/api/chat/{session_id}/continue")

    assert response.status_code == 409


@pytest.mark.parametrize("scripted_client", [OPENING_SCRIPT], indirect=True)
def test_continue_without_a_pending_confirm_hint_is_refused(scripted_client) -> None:
    session_id = _start(scripted_client)
    _stream(scripted_client, f"/api/chat/{session_id}/opening")

    # The check-in opens the step's multiple-choice question, so nothing is left to advance.
    _stream(scripted_client, f"/api/chat/{session_id}/continue")
    response = scripted_client.post(f"/api/chat/{session_id}/continue")

    assert response.status_code == 409


@pytest.mark.parametrize("scripted_client", [STEP_WALK_SCRIPT], indirect=True)
def test_two_turns_never_return_the_same_reply(scripted_client) -> None:
    session_id = _start(scripted_client)

    first, _ = _stream_turns(scripted_client, session_id, "weiter")
    second, _ = _stream_turns(scripted_client, session_id, "Ja, weiter")
    third, _ = _stream_turns(scripted_client, session_id, "B")

    replies = [events[-1]["text"] for events in (first, second, third)]
    assert len(set(replies)) == 3, replies
    # The step teaches, the check-in opens its case, and the answer settles it in words and
    # teaches the next step in the same reply (D89, D96).
    assert _first_chapter(scripted_client).steps[0].text in replies[0]
    assert replies[2].startswith("Richtig.")
    assert _first_chapter(scripted_client).steps[1].text in replies[2]
    # The answer turn names every step as it starts: the grade, then the voice's rewrite
    # and its check. A chip's reply is curated, so nothing is written or reply-checked
    # (D125).
    steps = [event["step"] for event in third if event["event"] == "working"]
    assert steps == ["reading", "grading", "voicing", "checking"]


@pytest.mark.parametrize("scripted_client", [VERDICT_WALK_SCRIPT], indirect=True)
def test_the_verdict_lands_before_the_reply_streams(scripted_client) -> None:
    session_id = _start(scripted_client)

    _stream_turns(scripted_client, session_id, "weiter")
    _stream_turns(scripted_client, session_id, "Ja, weiter")
    events, _ = _stream_turns(scripted_client, session_id, "B")

    names = {event["name"] for event in events if event["event"] == "ui"}
    assert {"answer_result", "confetti"} <= names
    first_token = next(index for index, event in enumerate(events) if event["event"] == "token")
    for name in ("answer_result", "confetti"):
        verdict = next(
            index
            for index, event in enumerate(events)
            if event["event"] == "ui" and event["name"] == name
        )
        assert verdict < first_token


@pytest.mark.parametrize("scripted_client", [FAILED_REWRITE_SCRIPT], indirect=True)
def test_the_streamed_text_is_the_settled_text(scripted_client) -> None:
    session_id = _start(scripted_client)

    events, _ = _stream_turns(scripted_client, session_id, "weiter")

    tokens = "".join(event["text"] for event in events if event["event"] == "token")
    message = events[-1]
    assert message["event"] == "message"
    # Nothing the student read may change when the turn settles: what streamed is
    # the whole, final text, whatever the persona threw away on the way.
    assert tokens == message["text"]


@pytest.mark.parametrize("scripted_client", [GRADE_SCRIPT], indirect=True)
def test_graded_answer_streams_result_card_and_statuses(scripted_client) -> None:
    session_id = _start(scripted_client)
    question = scripted_client.app.state.content.locales["de"].questions["q-02-04"]
    graph = scripted_client.app.state.graph
    config = {"configurable": {"thread_id": _thread_id(scripted_client, session_id)}}
    # Seed the thread mid-test the way tests/graph/test_graph.py's test flows do.
    # as_node="__start__" records the patch as graph input; a bare update cannot
    # be attributed on a thread whose only write so far is the seed.
    _run(
        graph.aupdate_state(
            config,
            {
                "phase": Phase.test,
                "attempts": 1,
                "test": RunningTest(question_ids=["q-02-04"]),
                "pending_prompt": "Frage 1 von 1",
            },
            as_node="__start__",
        )
    )

    events, _ = _stream_turns(scripted_client, session_id, CORRECT_FREE_TEXT_ANSWER)

    results = [
        event for event in events if event["event"] == "ui" and event["name"] == "answer_result"
    ]
    assert results == [
        {"event": "ui", "name": "answer_result", "payload": {"verdict": "correct", "settled": True}}
    ]
    cards = [event["part"] for event in events if event["event"] == "part"]
    # The last answer finishes the test: the card lands beside the cheat sheet (D128).
    assert [card["kind"] for card in cards] == ["card", "file"]
    assert cards[0]["correct"] is True
    assert [citation["ref"] for citation in cards[0]["citations"]] == [
        de_ref(citation) for citation in question.citations
    ]
    assert cards[0]["question"] == question.question
    message = events[-1]
    assert message["event"] == "message"
    assert message["parts"] == cards
    status_nodes = {event["node"] for event in events if event["event"] == "status"}
    assert {"grade", "persona"} <= status_nodes


@pytest.mark.parametrize("scripted_client", [TEST_HINT_SCRIPT], indirect=True)
def test_a_test_question_hint_never_carries_its_answer(scripted_client) -> None:
    session_id = _start(scripted_client)
    graph = scripted_client.app.state.graph
    config = {"configurable": {"thread_id": _thread_id(scripted_client, session_id)}}
    question = scripted_client.app.state.content.locales["de"].questions["q-01-11"]
    _run(
        graph.aupdate_state(
            config,
            {
                "phase": Phase.test,
                "attempts": 1,
                "test": RunningTest(question_ids=["q-01-11", "q-01-11"]),
                "pending_prompt": question.question,
            },
            as_node="__start__",
        )
    )

    events, _ = _stream_turns(scripted_client, session_id, question.correct)

    hints = [event["hint"] for event in events if event["event"] == "input_hint"]
    assert hints and hints[-1]["kind"] == "choices"
    # The next test question re-offers its options, and none of them names the
    # answer: the tutor does not give a test answer away, not even in the stream.
    assert all(hint.get("correct_key") is None for hint in hints)


@pytest.mark.parametrize("scripted_client", [ANSWER_THEN_STEP_SCRIPT], indirect=True)
def test_earlier_messages_keep_their_parts_after_a_later_turn(scripted_client) -> None:
    session_id = _start(scripted_client)
    opening_events, _ = _stream(scripted_client, f"/api/chat/{session_id}/opening")
    first_refs = [e["part"]["ref"] for e in opening_events if e["event"] == "part"]
    assert first_refs == ["Art. 3 Nr. 1", "Art. 3 Nr. 4"]

    # The check-in opens the case, and the answer settles it and runs on into the second
    # step, so the sources under it are that step's (D89, D96).
    _stream_turns(scripted_client, session_id, "Ja, weiter")
    second_events, _ = _stream_turns(scripted_client, session_id, "B")
    second_refs = [e["part"]["ref"] for e in second_events if e["event"] == "part"]
    # The verdict's own sources stand with the next step's in that one turn.
    assert second_refs == [
        "Art. 3 Nr. 1",
        "Art. 3 Nr. 4",
        "Art. 4 Abs. 1",
        "Q&A der Kommission 14",
    ]
    _stream_turns(scripted_client, session_id, "weiter")

    messages = scripted_client.get("/api/session").json()["messages"]
    assert [m["role"] for m in messages] == [
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    # The step's own sources stay with the step, the answer's with the answer.
    assert [p["ref"] for p in messages[0]["parts"]] == ["Art. 3 Nr. 1", "Art. 3 Nr. 4"]
    assert messages[1]["parts"] == []
    assert messages[2]["parts"] == []
    assert [p["ref"] for p in messages[4]["parts"]] == second_refs
    assert messages[6]["parts"] == []


def test_turn_requires_sign_in(client) -> None:
    response = client.post("/api/chat/1/turns", json={"text": "Hallo"})
    assert response.status_code == 401


def test_turn_rejects_empty_text(scripted_client) -> None:
    session_id = _start(scripted_client)
    response = scripted_client.post(f"/api/chat/{session_id}/turns", json={"text": ""})
    assert response.status_code == 422


def test_turn_rejects_overlong_text(scripted_client) -> None:
    session_id = _start(scripted_client)
    response = scripted_client.post(f"/api/chat/{session_id}/turns", json={"text": "x" * 4001})
    assert response.status_code == 422


def test_turn_of_foreign_session_is_404(scripted_client) -> None:
    anna_id = _start(scripted_client)
    scripted_client.post("/api/auth/dev/logout")
    scripted_client.post("/api/auth/dev/login", json={"subject": "boris"})
    response = scripted_client.post(f"/api/chat/{anna_id}/turns", json={"text": "Hallo"})
    assert response.status_code == 404


@pytest.mark.parametrize("scripted_client", [BROKEN_SCRIPT], indirect=True)
def test_graph_failure_streams_an_error_event(scripted_client) -> None:
    session_id = _start(scripted_client)

    with scripted_client.stream(
        "POST", f"/api/chat/{session_id}/turns", json={"text": "Hallo"}
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        lines = list(response.iter_lines())

    events = [json.loads(line[6:]) for line in lines if line.startswith("data: ")]
    assert events[0]["event"] == "status"
    assert events[-1] == {
        "event": "error",
        "code": "turn_failed",
        "message": "chat.error",
        "budget": None,
    }


def test_a_token_with_a_newline_stays_one_frame() -> None:
    frame = format_sse(TokenEvent(text="Zeile 1\nZeile 2"))
    assert frame.count("data: ") == 1


@pytest.mark.parametrize("scripted_client", [LESSON_SCRIPT], indirect=True)
def test_the_message_stores_its_hint_next_to_its_parts(scripted_client) -> None:
    session_id = _start(scripted_client)
    _stream_turns(scripted_client, session_id, "weiter")
    events, _ = _stream_turns(scripted_client, session_id, "Ja, weiter")

    config = {"configurable": {"thread_id": _thread_id(scripted_client, session_id)}}
    values = _run(scripted_client.app.state.graph.aget_state(config)).values
    last = values["messages"][-1]
    assert last.additional_kwargs["hint"] == events[-1]["hint"]
    assert last.additional_kwargs["hint"]["kind"] == "choices"


def test_a_chosen_option_replays_as_the_sentence_the_student_pressed(scripted_client) -> None:
    session_id = _start(scripted_client)
    _stream(scripted_client, f"/api/chat/{session_id}/opening")
    _stream(
        scripted_client,
        f"/api/chat/{session_id}/turns",
        {
            "text": "B",
            "shown": "B. Sie ist ein KI-System, und unser Unternehmen ist ihr Betreiber.",
        },
    )

    messages = scripted_client.get("/api/session").json()["messages"]
    said = [m["text"] for m in messages if m["role"] == "user"]

    assert said == ["B. Sie ist ein KI-System, und unser Unternehmen ist ihr Betreiber."]


def test_a_stored_part_this_build_cannot_render_is_dropped_not_fatal() -> None:
    from app.api.chat import _readable

    # The shape a card carried before its citations became citation parts.
    old_card = {"kind": "card", "card": {"question": "Q", "answer": "A", "citations": ["Art. 3"]}}
    citation = {"kind": "citations", "ref": "Art. 3", "title": "t", "quote": "q", "url": "u"}

    kept = _readable([old_card, citation])

    assert [part.kind for part in kept] == ["citations"]
