from fastapi.testclient import TestClient


def test_theme_serves_configured_colors_without_login(client: TestClient) -> None:
    response = client.get("/api/theme")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"primary", "secondary", "accent", "background", "look"}
    assert body["look"] in ("pixel", "clean")
    assert response.headers["cache-control"] == "public, max-age=300"
