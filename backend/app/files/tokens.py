from itsdangerous import URLSafeSerializer

from app.graph.state import FilePart
from app.i18n import t
from app.settings import Settings

FILE_TOKEN_SALT = "files"


def _serializer(settings: Settings) -> URLSafeSerializer:
    return URLSafeSerializer(settings.secret_key, salt=FILE_TOKEN_SALT)


def chapter_token(settings: Settings, chapter_id: str, locale: str, course_version: str) -> str:
    return _serializer(settings).dumps(
        {"kind": "cheat-chapter", "chapter": chapter_id, "locale": locale, "cv": course_version}
    )


def full_token(settings: Settings, locale: str, course_version: str) -> str:
    return _serializer(settings).dumps(
        {"kind": "cheat-full", "locale": locale, "cv": course_version}
    )


def certificate_token(
    settings: Settings,
    *,
    user_id: int,
    score: int,
    total: int,
    passed: bool,
    passed_on: str,
    locale: str,
    course_version: str,
    law_version: str,
) -> str:
    return _serializer(settings).dumps(
        {
            "kind": "certificate",
            "uid": user_id,
            "score": score,
            "total": total,
            "passed": passed,
            "passed_on": passed_on,
            "locale": locale,
            "cv": course_version,
            "lv": law_version,
        }
    )


def read_file_token(settings: Settings, token: str) -> dict:
    """The payload of a token this process signed; raises BadSignature otherwise."""
    return _serializer(settings).loads(token)


def _file_url(token: str) -> str:
    return f"/api/files/{token}"


def chapter_file_part(
    settings: Settings, locale: str, course_version: str, chapter_id: str, chapter_title: str
) -> FilePart:
    return FilePart(
        url=_file_url(chapter_token(settings, chapter_id, locale, course_version)),
        title=t(locale, "cheatsheet_chapter_title", title=chapter_title),
        filename=f"spickzettel-{chapter_id}.pdf",
    )


def full_file_part(settings: Settings, locale: str, course_version: str) -> FilePart:
    return FilePart(
        url=_file_url(full_token(settings, locale, course_version)),
        title=t(locale, "cheatsheet_full_title"),
        filename="spickzettel-kurs.pdf",
    )


def certificate_file_part(
    settings: Settings,
    *,
    user_id: int,
    score: int,
    total: int,
    passed: bool,
    passed_on: str,
    locale: str,
    course_version: str,
    law_version: str,
) -> FilePart:
    return FilePart(
        url=_file_url(
            certificate_token(
                settings,
                user_id=user_id,
                score=score,
                total=total,
                passed=passed,
                passed_on=passed_on,
                locale=locale,
                course_version=course_version,
                law_version=law_version,
            )
        ),
        title=t(locale, "certificate_title"),
        filename="zertifikat.pdf",
    )
