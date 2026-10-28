from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


def make_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>trainer</body></html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return dist


def test_serves_index_assets_and_spa_fallback(settings: Settings, tmp_path: Path):
    settings = settings.model_copy(update={"frontend_dist": make_dist(tmp_path)})
    with TestClient(create_app(settings)) as client:
        assert client.get("/").text == "<html><body>trainer</body></html>"
        assert client.get("/assets/app.js").text == "console.log(1)"
        assert client.get("/some/client/route").text == "<html><body>trainer</body></html>"
        assert client.get("/api/health/live").json() == {"status": "ok"}
        assert client.get("/api/nope").status_code == 404


def test_the_index_page_may_never_be_served_from_heuristic_cache(
    settings: Settings, tmp_path: Path
):
    """The index page names the hashed bundles; a stale one runs the old app. Without
    an explicit Cache-Control the browser heuristically caches it and a deploy never
    reaches a tab that reloads."""
    settings = settings.model_copy(update={"frontend_dist": make_dist(tmp_path)})
    with TestClient(create_app(settings)) as client:
        for path in ["/", "/some/client/route"]:
            response = client.get(path)
            assert response.headers["cache-control"] == "no-cache"


def test_serves_a_file_that_sits_at_the_dist_root(settings: Settings, tmp_path: Path):
    favicon = '<svg xmlns="http://www.w3.org/2000/svg" />'
    dist = make_dist(tmp_path)
    (dist / "favicon.svg").write_text(favicon, encoding="utf-8")
    settings = settings.model_copy(update={"frontend_dist": dist})
    with TestClient(create_app(settings)) as client:
        response = client.get("/favicon.svg")
        assert response.status_code == 200
        assert response.text == favicon


def test_missing_dist_leaves_api_working(client: TestClient):
    assert client.get("/api/health/live").status_code == 200
    assert client.get("/").status_code == 404


def test_bare_api_path_is_not_the_spa(settings: Settings, tmp_path: Path):
    settings = settings.model_copy(update={"frontend_dist": make_dist(tmp_path)})
    with TestClient(create_app(settings)) as client:
        assert client.get("/api").status_code == 404
        assert client.get("/api/").status_code == 404


def test_traversal_outside_dist_is_not_served(settings: Settings, tmp_path: Path):
    dist = make_dist(tmp_path)
    (tmp_path / "secret.txt").write_text("outside", encoding="utf-8")
    settings = settings.model_copy(update={"frontend_dist": dist})
    with TestClient(create_app(settings)) as client:
        response = client.get("/%2e%2e/secret.txt")
        assert response.status_code == 200
        assert response.text == "<html><body>trainer</body></html>"
        assert "outside" not in response.text
