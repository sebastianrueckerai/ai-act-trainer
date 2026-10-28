from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.files import pdf as pdf_module
from app.files import router as files_router
from app.files.tokens import certificate_token, chapter_token, full_token
from app.storage.repository import SqlAlchemyRepository


@pytest.fixture
def fake_render(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(pdf_module, "_write_pdf", lambda html, fonts_dir: b"%PDF-fake")
    pdf_module._chapter_cache.clear()
    yield
    pdf_module._chapter_cache.clear()


def _login(client: TestClient, subject: str) -> None:
    assert client.post("/api/auth/dev/login", json={"subject": subject}).status_code == 200


def _repo_user_id(client: TestClient, subject: str) -> int:
    with Session(client.app.state.engine) as session:
        repo = SqlAlchemyRepository(session)
        user = repo.upsert_user(subject, subject.title(), f"{subject}@example.test", [])
        uid = user.id
        session.commit()
        return uid


def test_files_require_login(client: TestClient) -> None:
    assert client.get("/api/files/anything").status_code == 401


def test_bad_token_is_404(client: TestClient, fake_render: None) -> None:
    _login(client, "anna")

    assert client.get("/api/files/not-a-token").status_code == 404


def test_chapter_cheat_serves_any_authenticated_student(
    client: TestClient, fake_render: None
) -> None:
    _login(client, "boris")
    token = chapter_token(client.app.state.settings, "01-warum-es-dich-betrifft", "de", "v0.1")

    response = client.get(f"/api/files/{token}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-fake"
    assert (
        response.headers["content-disposition"]
        == 'inline; filename="spickzettel-01-warum-es-dich-betrifft.pdf"'
    )
    assert response.headers["cache-control"] == "private, max-age=3600"


def test_a_token_for_a_chapter_that_no_longer_exists_is_404(
    client: TestClient, fake_render: None
) -> None:
    _login(client, "anna")
    token = chapter_token(client.app.state.settings, "99-weggeraeumt", "de", "v0.1")

    assert client.get(f"/api/files/{token}").status_code == 404


def test_a_chapter_token_for_an_unbundled_locale_is_404(
    client: TestClient, fake_render: None
) -> None:
    _login(client, "anna")
    token = chapter_token(client.app.state.settings, "01-warum-es-dich-betrifft", "en", "v0.1")

    assert client.get(f"/api/files/{token}").status_code == 404


def test_a_chapter_token_for_a_locale_with_strings_but_no_content_is_404(
    client: TestClient, fake_render: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(files_router, "has_locale", lambda locale: True)
    _login(client, "anna")
    token = chapter_token(client.app.state.settings, "01-warum-es-dich-betrifft", "fr", "v0.1")

    assert client.get(f"/api/files/{token}").status_code == 404


def test_a_chapter_token_for_a_locale_without_strings_is_404(
    client: TestClient, fake_render: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(files_router, "has_locale", lambda locale: False)
    _login(client, "anna")
    token = chapter_token(client.app.state.settings, "01-warum-es-dich-betrifft", "de", "v0.1")

    assert client.get(f"/api/files/{token}").status_code == 404


def test_full_cheat_serves_any_authenticated_student(client: TestClient, fake_render: None) -> None:
    _login(client, "anna")
    token = full_token(client.app.state.settings, "de", "v0.1")

    assert client.get(f"/api/files/{token}").status_code == 200


def test_a_full_cheat_token_for_an_unbundled_locale_is_404(
    client: TestClient, fake_render: None
) -> None:
    _login(client, "anna")
    token = full_token(client.app.state.settings, "en", "v0.1")

    assert client.get(f"/api/files/{token}").status_code == 404


def test_a_full_cheat_token_for_a_locale_with_strings_but_no_content_is_404(
    client: TestClient, fake_render: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(files_router, "has_locale", lambda locale: True)
    _login(client, "anna")
    token = full_token(client.app.state.settings, "fr", "v0.1")

    assert client.get(f"/api/files/{token}").status_code == 404


def test_a_full_cheat_token_for_a_locale_without_strings_is_404(
    client: TestClient, fake_render: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(files_router, "has_locale", lambda locale: False)
    _login(client, "anna")
    token = full_token(client.app.state.settings, "de", "v0.1")

    assert client.get(f"/api/files/{token}").status_code == 404


def test_certificate_serves_only_its_owner(client: TestClient, fake_render: None) -> None:
    _login(client, "anna")
    anna_id = _repo_user_id(client, "anna")
    boris_id = _repo_user_id(client, "boris")

    def _token(uid: int, locale: str = "de") -> str:
        return certificate_token(
            client.app.state.settings,
            user_id=uid,
            score=10,
            total=10,
            passed=True,
            passed_on="2026-09-19",
            locale=locale,
            course_version="v0.1",
            law_version="02024R1689-20260727",
        )

    assert client.get(f"/api/files/{_token(anna_id)}").status_code == 200
    assert client.get(f"/api/files/{_token(boris_id)}").status_code == 403
    assert client.get(f"/api/files/{_token(boris_id, 'fr')}").status_code == 403


def test_a_certificate_token_for_a_locale_without_strings_is_404(
    client: TestClient, fake_render: None
) -> None:
    _login(client, "anna")
    token = certificate_token(
        client.app.state.settings,
        user_id=_repo_user_id(client, "anna"),
        score=10,
        total=10,
        passed=True,
        passed_on="2026-09-19",
        locale="fr",
        course_version="v0.1",
        law_version="02024R1689-20260727",
    )

    assert client.get(f"/api/files/{token}").status_code == 404
