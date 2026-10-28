from tests.api.test_turns import _start, _stream_turns


def test_session_response_carries_stage(scripted_client) -> None:
    scripted_client.post("/api/auth/dev/login", json={"subject": "anna"})
    response = scripted_client.post("/api/session", json={"persona_id": "sergeant"})

    assert response.status_code == 200
    stage = response.json()["stage"]
    assert len(stage["chapters"]) == 8
    assert stage["persona"]["id"] == "sergeant"
    assert stage["persona"]["name"] == "Der Feldwebel"
    assert stage["attempt"] is None


def test_turn_emits_stage_event(scripted_client) -> None:
    session_id = _start(scripted_client, "pirate")
    events, _ = _stream_turns(scripted_client, session_id, "hallo")

    stage_events = [
        event for event in events if event["event"] == "ui" and event["name"] == "stage"
    ]
    assert len(stage_events) == 1
    payload = stage_events[0]["payload"]
    assert len(payload["chapters"]) == 8
    assert payload["mood"] == "neutral"
    assert payload["persona"]["id"] == "pirate"
    # The step teaches first, so its case is not open yet (D96).
    assert payload["attempt"] is None
