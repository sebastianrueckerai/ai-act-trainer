import pytest
from itsdangerous import BadSignature

from app.files.tokens import (
    certificate_file_part,
    certificate_token,
    chapter_file_part,
    chapter_token,
    full_file_part,
    full_token,
    read_file_token,
)
from app.settings import Settings


def _settings() -> Settings:
    return Settings(
        env="test", database_url="sqlite:///:memory:", secret_key="test-secret-key-16ch"
    )


def _payload(settings: Settings, url: str) -> dict:
    return read_file_token(settings, url.removeprefix("/api/files/"))


def test_chapter_token_round_trip() -> None:
    settings = _settings()
    token = chapter_token(settings, "01-warum-es-dich-betrifft", "de", "v0.1")

    payload = read_file_token(settings, token)
    assert payload == {
        "kind": "cheat-chapter",
        "chapter": "01-warum-es-dich-betrifft",
        "locale": "de",
        "cv": "v0.1",
    }


def test_full_token_round_trip() -> None:
    settings = _settings()
    payload = read_file_token(settings, full_token(settings, "de", "v0.1"))
    assert payload == {"kind": "cheat-full", "locale": "de", "cv": "v0.1"}


def test_certificate_token_round_trip() -> None:
    settings = _settings()
    token = certificate_token(
        settings,
        user_id=7,
        score=9,
        total=10,
        passed=True,
        passed_on="2026-09-19",
        locale="de",
        course_version="v0.1",
        law_version="02024R1689-20260727",
    )
    payload = read_file_token(settings, token)
    assert payload == {
        "kind": "certificate",
        "uid": 7,
        "score": 9,
        "total": 10,
        "passed": True,
        "passed_on": "2026-09-19",
        "locale": "de",
        "cv": "v0.1",
        "lv": "02024R1689-20260727",
    }


def test_tampered_token_is_rejected() -> None:
    settings = _settings()
    token = full_token(settings, "de", "v0.1")
    with pytest.raises(BadSignature):
        read_file_token(settings, token + "x")


def test_tokens_from_another_secret_are_rejected() -> None:
    other = Settings(env="test", database_url="sqlite:///:memory:", secret_key="another-secret-key")
    token = full_token(_settings(), "de", "v0.1")
    with pytest.raises(BadSignature):
        read_file_token(other, token)


def test_chapter_file_part_carries_its_token_and_the_german_title() -> None:
    settings = _settings()
    part = chapter_file_part(
        settings, "de", "v0.1", "01-warum-es-dich-betrifft", "Warum es dich betrifft"
    )

    assert part.title == "Spickzettel: Warum es dich betrifft"
    assert part.filename == "spickzettel-01-warum-es-dich-betrifft.pdf"
    assert _payload(settings, part.url) == {
        "kind": "cheat-chapter",
        "chapter": "01-warum-es-dich-betrifft",
        "locale": "de",
        "cv": "v0.1",
    }


def test_full_file_part_carries_its_token_and_the_german_title() -> None:
    settings = _settings()
    part = full_file_part(settings, "de", "v0.1")

    assert part.title == "Spickzettel: Der ganze Kurs"
    assert part.filename == "spickzettel-kurs.pdf"
    assert _payload(settings, part.url) == {"kind": "cheat-full", "locale": "de", "cv": "v0.1"}


def test_certificate_file_part_carries_its_token_and_the_german_title() -> None:
    settings = _settings()
    part = certificate_file_part(
        settings,
        user_id=7,
        score=9,
        total=10,
        passed=True,
        passed_on="2026-09-19",
        locale="de",
        course_version="v0.1",
        law_version="02024R1689-20260727",
    )

    assert part.title == "Zertifikat"
    assert part.filename == "zertifikat.pdf"
    assert _payload(settings, part.url)["kind"] == "certificate"
