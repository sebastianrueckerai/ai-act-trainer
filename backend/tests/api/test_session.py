import asyncio

import httpx
from langchain_core.messages import HumanMessage
from sqlalchemy import select

from app.storage.models import TrainingSession
from app.storage.repository import SqlAlchemyRepository


def _run(coro):
    return asyncio.run(coro)


def _thread_id(client, session_id: int) -> str:
    with client.app.state.session_factory() as db:
        training_session = db.scalar(
            select(TrainingSession).where(TrainingSession.id == session_id)
        )
    assert training_session is not None
    return training_session.thread_id


def test_session_requires_sign_in(client) -> None:
    response = client.post("/api/session", json={"persona_id": "clerk"})
    assert response.status_code == 401


def test_a_fresh_session_starts_the_lesson_with_the_chosen_persona(scripted_client) -> None:
    scripted_client.post("/api/auth/dev/login", json={"subject": "anna"})
    response = scripted_client.post("/api/session", json={"persona_id": "jester"})
    assert response.status_code == 200
    body = response.json()
    assert body["persona_id"] == "jester"
    assert body["phase"] == "lesson"
    assert body["messages"] == []
    assert body["hint"]["kind"] == "text"
    assert body["stage"]["persona"]["name"] == "Der Hofnarr"


def test_an_unknown_persona_is_rejected(scripted_client) -> None:
    scripted_client.post("/api/auth/dev/login", json={"subject": "anna"})
    response = scripted_client.post("/api/session", json={"persona_id": "kapitaen-nemo"})
    assert response.status_code == 422


def test_there_is_no_active_session_before_a_persona_is_picked(scripted_client) -> None:
    scripted_client.post("/api/auth/dev/login", json={"subject": "anna"})
    assert scripted_client.get("/api/session").status_code == 404


def test_the_active_session_resumes_the_thread(scripted_client) -> None:
    scripted_client.post("/api/auth/dev/login", json={"subject": "anna"})
    created = scripted_client.post("/api/session", json={"persona_id": "clerk"}).json()
    resumed = scripted_client.get("/api/session")
    assert resumed.status_code == 200
    assert resumed.json()["id"] == created["id"]
    assert resumed.json()["persona_id"] == "clerk"


def test_session_returns_recent_messages(scripted_client) -> None:
    scripted_client.post("/api/auth/dev/login", json={"subject": "anna"})
    created = scripted_client.post("/api/session", json={"persona_id": "clerk"}).json()
    config = {"configurable": {"thread_id": _thread_id(scripted_client, created["id"])}}
    graph = scripted_client.app.state.graph
    # as_node="__start__" records the message as graph input; a bare update cannot
    # be attributed on a thread whose only write so far is the seed.
    _run(graph.aupdate_state(config, {"messages": [HumanMessage("Hallo")]}, as_node="__start__"))

    response = scripted_client.get("/api/session")

    assert response.status_code == 200
    body = response.json()
    assert body["phase"] == "lesson"
    [message] = body["messages"]
    assert message["id"]
    assert {k: v for k, v in message.items() if k != "id"} == {
        "role": "user",
        "text": "Hallo",
        "parts": [],
        "hint": None,
        "translating": False,
    }
    assert body["hint"]["kind"] == "text"


def test_session_of_another_user_is_not_found(scripted_client) -> None:
    scripted_client.post("/api/auth/dev/login", json={"subject": "anna"})
    anna_id = scripted_client.post("/api/session", json={"persona_id": "clerk"}).json()["id"]
    scripted_client.post("/api/auth/dev/logout")
    scripted_client.post("/api/auth/dev/login", json={"subject": "boris"})
    boris = scripted_client.post("/api/session", json={"persona_id": "marvin"}).json()
    assert boris["id"] != anna_id

    with scripted_client.app.state.session_factory() as db:
        repo = SqlAlchemyRepository(db)
        anna_user = repo.upsert_user("anna", "Anna Beispiel", "anna@example.org", ["staff"])
        boris_user = repo.upsert_user(
            "boris", "Boris Muster", "boris@example.org", ["staff", "compliance"]
        )
        assert repo.get_session(anna_id, boris_user.id) is None
        assert repo.get_session(anna_id, anna_user.id) is not None


def test_closing_the_active_session_lets_a_new_one_start(scripted_client) -> None:
    scripted_client.post("/api/auth/dev/login", json={"subject": "anna"})
    first = scripted_client.post("/api/session", json={"persona_id": "clerk"}).json()

    response = scripted_client.post("/api/session/close")

    assert response.status_code == 204
    assert scripted_client.get("/api/session").status_code == 404
    with scripted_client.app.state.session_factory() as db:
        closed = db.get(TrainingSession, first["id"])
        assert closed.status == "abandoned"
        assert closed.closed_at is not None

    second = scripted_client.post("/api/session", json={"persona_id": "clerk"}).json()
    assert second["id"] != first["id"]


def test_closing_session_requires_sign_in(client) -> None:
    response = client.post("/api/session/close")
    assert response.status_code == 401


def test_closing_with_no_active_session_is_a_404(scripted_client) -> None:
    scripted_client.post("/api/auth/dev/login", json={"subject": "anna"})
    response = scripted_client.post("/api/session/close")
    assert response.status_code == 404


def test_a_session_starts_with_the_requested_display_locale(scripted_client) -> None:
    scripted_client.post("/api/auth/dev/login", json={"subject": "anna"})
    # An English stage renders the chapter titles once.
    scripted_client.app.state.deps.models["fast"].script["translate_fields"] = "1: Chapter 1"
    response = scripted_client.post(
        "/api/session", json={"persona_id": "pirate", "display_locale": "en"}
    )
    assert response.status_code == 200
    assert response.json()["display_locale"] == "en"


def test_the_display_locale_defaults_to_german(scripted_client) -> None:
    scripted_client.post("/api/auth/dev/login", json={"subject": "anna"})
    response = scripted_client.post("/api/session", json={"persona_id": "pirate"})
    assert response.json()["display_locale"] == "de"


def test_the_display_locale_can_be_switched_on_a_live_session(scripted_client) -> None:
    scripted_client.post("/api/auth/dev/login", json={"subject": "anna"})
    scripted_client.app.state.deps.models["fast"].script["translate_fields"] = "1: Chapter 1"
    session = scripted_client.post("/api/session", json={"persona_id": "pirate"}).json()
    response = scripted_client.put(
        f"/api/session/{session['id']}/display-locale", json={"display_locale": "en"}
    )
    assert response.status_code == 200
    assert response.json()["display_locale"] == "en"
    assert scripted_client.get("/api/session").json()["display_locale"] == "en"


def test_an_unknown_display_locale_is_rejected(scripted_client) -> None:
    scripted_client.post("/api/auth/dev/login", json={"subject": "anna"})
    session = scripted_client.post("/api/session", json={"persona_id": "pirate"}).json()
    response = scripted_client.put(
        f"/api/session/{session['id']}/display-locale", json={"display_locale": "fr"}
    )
    assert response.status_code == 422


class _YieldingGraph:
    # The scripted graph never yields where production awaits checkpoint I/O; the pause
    # must outlast the other request's dispatch, and sleep(0) does not.
    def __init__(self, graph):
        self._graph = graph

    async def aget_state(self, config):
        await asyncio.sleep(0.05)
        return await self._graph.aget_state(config)

    async def aupdate_state(self, config, values, as_node=None):
        await asyncio.sleep(0.05)
        return await self._graph.aupdate_state(config, values, as_node=as_node)


def test_concurrent_session_bootstraps_for_same_subject_both_complete(
    scripted_client,
) -> None:
    scripted_client.app.state.graph = _YieldingGraph(scripted_client.app.state.graph)

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=scripted_client.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
            await http.post("/api/auth/dev/login", json={"subject": "anna"})
            body = {"persona_id": "clerk"}
            first, second = await asyncio.wait_for(
                asyncio.gather(
                    http.post("/api/session", json=body), http.post("/api/session", json=body)
                ),
                timeout=30,
            )
        return first, second

    first, second = _run(scenario())

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
