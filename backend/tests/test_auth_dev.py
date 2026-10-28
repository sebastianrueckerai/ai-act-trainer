from fastapi.testclient import TestClient
from itsdangerous import URLSafeTimedSerializer

from app.auth.factory import build_session_cookie
from app.auth.identity import assign_roles
from app.auth.session import COOKIE_NAME
from app.settings import Settings


def test_assign_roles_gives_everyone_student_and_admins_admin():
    assert assign_roles(["staff"], ["compliance"]) == ["student"]
    assert assign_roles(["staff", "compliance"], ["compliance"]) == ["student", "admin"]


def test_dev_users_are_listed(client: TestClient):
    body = client.get("/api/auth/dev/users").json()
    assert [user["subject"] for user in body] == ["demo", "anna", "boris"]


def test_me_requires_login(client: TestClient):
    assert client.get("/api/me").status_code == 401


def test_dev_login_sets_cookie_and_me_reports_principal(client: TestClient):
    response = client.post("/api/auth/dev/login", json={"subject": "boris"})
    assert response.status_code == 200
    assert "trainer_session" in response.cookies
    body = client.get("/api/me").json()
    assert body["principal"] == {
        "subject": "boris",
        "name": "Boris Muster",
        "email": "boris@example.org",
        "groups": ["staff", "compliance"],
        "roles": ["student", "admin"],
    }
    assert body["data_level"] == 0
    assert body["stored"] == ["pass_date", "course_version", "law_version", "locale", "persona"]


def test_dev_login_cookie_is_httponly_lax_and_not_secure(client: TestClient):
    response = client.post("/api/auth/dev/login", json={"subject": "anna"})
    header = response.headers["set-cookie"]
    assert header.startswith(f"{COOKIE_NAME}=")
    assert "HttpOnly" in header
    assert "SameSite=lax" in header
    assert "Secure" not in header


def test_session_cookie_is_secure_in_production():
    production = Settings(
        _env_file=None, env="production", auth_backend="oidc", secret_key="x" * 32
    )
    assert build_session_cookie(production).secure is True


def test_fresh_subject_logs_in_as_plain_student(client: TestClient):
    response = client.post("/api/auth/dev/login", json={"subject": "m4walk"})
    assert response.status_code == 200
    body = client.get("/api/me").json()
    assert body["principal"]["subject"] == "m4walk"
    assert body["principal"]["groups"] == []
    assert body["principal"]["roles"] == ["student"]


def test_blank_subject_is_rejected(client: TestClient):
    assert client.post("/api/auth/dev/login", json={"subject": ""}).status_code == 422


def test_logout_clears_cookie(client: TestClient):
    client.post("/api/auth/dev/login", json={"subject": "anna"})
    assert client.get("/api/me").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/me").status_code == 401


def test_tampered_cookie_is_rejected(client: TestClient):
    client.post("/api/auth/dev/login", json={"subject": "anna"})
    client.cookies.set("trainer_session", "not-a-valid-token")
    assert client.get("/api/me").status_code == 401


def test_correctly_signed_cookie_without_a_subject_is_rejected(
    client: TestClient, settings: Settings
):
    serializer = URLSafeTimedSerializer(settings.secret_key, salt="trainer-session")
    client.cookies.set(COOKIE_NAME, serializer.dumps({"name": "Anna Beispiel"}))
    assert client.get("/api/me").status_code == 401


def test_dev_routes_absent_for_other_backends(settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    settings = settings.model_copy(
        update={"auth_backend": "proxy", "proxy_trusted_addresses": ["10.0.0.1"]}
    )
    try:
        app = create_app(settings)
    except NotImplementedError as exc:
        assert "proxy" in str(exc)
        return
    with TestClient(app) as other:
        assert other.get("/api/auth/dev/users").status_code == 404
