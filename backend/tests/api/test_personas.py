from fastapi.testclient import TestClient


def _login(client: TestClient, subject: str = "anna") -> None:
    response = client.post("/api/auth/dev/login", json={"subject": subject})
    assert response.status_code == 200


def test_personas_require_login(client: TestClient) -> None:
    assert client.get("/api/personas").status_code == 401


def test_personas_list_names_and_image_urls(client: TestClient) -> None:
    _login(client)
    response = client.get("/api/personas")

    assert response.status_code == 200
    personas = response.json()
    assert {p["id"] for p in personas} == {"clerk", "jester", "marvin", "pirate", "sergeant"}
    marvin = next(p for p in personas if p["id"] == "marvin")
    assert marvin["name"]["de"] == "Depressobot"
    assert marvin["images"] == {"neutral": "/api/personas/marvin/images/neutral"}
    assert marvin["scene"] == "/api/personas/marvin/images/scene"


def test_personas_declare_only_the_frames_they_carry(client: TestClient) -> None:
    _login(client)
    personas = {p["id"]: p for p in client.get("/api/personas").json()}

    assert set(personas["clerk"]["images"]) == {"neutral", "happy", "disappointed"}
    assert set(personas["sergeant"]["images"]) == {"neutral", "happy", "disappointed"}
    assert set(personas["pirate"]["images"]) == {"neutral", "happy", "disappointed"}
    assert set(personas["jester"]["images"]) == {"neutral", "disappointed"}


def test_persona_image_serves_existing_png(client: TestClient) -> None:
    _login(client)

    response = client.get("/api/personas/clerk/images/happy")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "private, max-age=3600"
    assert response.content.startswith(b"\x89PNG")

    assert client.get("/api/personas/marvin/images/happy").status_code == 404
    assert client.get("/api/personas/clerk/images/nope").status_code == 404
    assert client.get("/api/personas/ghost/images/happy").status_code == 404


def test_persona_image_serves_the_scene_besides_the_emotions(client: TestClient) -> None:
    _login(client)

    response = client.get("/api/personas/marvin/images/scene")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")
