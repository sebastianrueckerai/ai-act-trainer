from fastapi.testclient import TestClient


def test_live(client: TestClient):
    response = client.get("/api/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_after_startup(client: TestClient):
    response = client.get("/api/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {
        "startup": True,
        "database": True,
        "database_error": None,
        "content": True,
    }


def test_ready_reports_503_while_startup_is_unfinished(client: TestClient):
    client.app.state.ready = False
    try:
        response = client.get("/api/health/ready")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "not-ready"
        assert body["checks"]["startup"] is False
    finally:
        client.app.state.ready = True


def test_ready_reports_a_generic_database_error(client: TestClient):
    class BrokenEngine:
        def connect(self):
            raise RuntimeError("postgresql://trainer:secret@db.internal:5432 refused")

    engine = client.app.state.engine
    client.app.state.engine = BrokenEngine()
    try:
        response = client.get("/api/health/ready")
    finally:
        client.app.state.engine = engine
    assert response.status_code == 503
    body = response.json()["checks"]
    assert body["database"] is False
    assert body["database_error"] == "database unavailable"
    assert "secret" not in response.text
