from fastapi import APIRouter, Depends, HTTPException, Request, Response
from itsdangerous import BadSignature

from app.api.deps import current_principal, get_repository, user_id
from app.api.version import law_version
from app.auth.identity import Principal
from app.content.loader import ContentBundle
from app.files import pdf
from app.files.tokens import read_file_token
from app.i18n import has_locale
from app.storage.repository import Repository

router = APIRouter(prefix="/api/files", tags=["files"])


def _require_strings(locale: str) -> None:
    if not has_locale(locale):
        raise HTTPException(status_code=404)


def _require_content(content: ContentBundle, locale: str) -> None:
    if locale not in content.locales:
        raise HTTPException(status_code=404)


@router.get("/{token}")
def get_file(
    token: str,
    request: Request,
    principal: Principal = Depends(current_principal),
    repo: Repository = Depends(get_repository),
) -> Response:
    settings = request.app.state.settings
    try:
        payload = read_file_token(settings, token)
    except BadSignature:
        raise HTTPException(status_code=404) from None

    kind = payload.get("kind")
    content = request.app.state.content
    if kind == "cheat-chapter":
        _require_strings(payload["locale"])
        _require_content(content, payload["locale"])
        if payload["chapter"] not in content.locales[payload["locale"]].chapters:
            raise HTTPException(status_code=404)
        document = pdf.render_chapter_cheat(
            settings, content, payload["chapter"], payload["locale"]
        )
        filename = f"spickzettel-{payload['chapter']}.pdf"
    elif kind == "cheat-full":
        _require_strings(payload["locale"])
        _require_content(content, payload["locale"])
        version = law_version(
            request.app.state.library, request.app.state.manifest.law.amended_by
        ).celex
        document = pdf.render_full_cheat(settings, content, payload["locale"], version)
        filename = "spickzettel-kurs.pdf"
    elif kind == "certificate":
        if payload["uid"] != user_id(principal, repo):
            raise HTTPException(status_code=403)
        _require_strings(payload["locale"])
        facts = pdf.CertificateFacts(
            score=payload["score"],
            total=payload["total"],
            passed=payload["passed"],
            passed_on=payload["passed_on"],
            course_version=payload["cv"],
            law_version=payload["lv"],
        )
        name = principal.name or principal.subject
        document = pdf.render_certificate(settings, payload["locale"], name, facts)
        filename = "zertifikat.pdf"
    else:
        raise HTTPException(status_code=404)

    return Response(
        content=document,
        media_type="application/pdf",
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )
