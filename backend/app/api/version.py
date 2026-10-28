from datetime import date

from fastapi import APIRouter, Request

from app.api.models import ActInfo, LawVersion, VersionInfo
from app.corpus.model import Library
from app.version import APP_VERSION

router = APIRouter(tags=["version"])


def law_version(library: Library, amended_by: list[str]) -> LawVersion:
    """A consolidated CELEX ends in its date: 02024R1689-20260727 is the text of 2026-07-27."""
    version = library.acts["ai_act"].version
    stamp = version.rsplit("-", 1)[1]
    return LawVersion(
        celex=version,
        consolidated=date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:])),
        amended_by=amended_by,
    )


@router.get("/version")
def version(request: Request) -> VersionInfo:
    manifest = request.app.state.manifest
    library = request.app.state.library
    return VersionInfo(
        app=APP_VERSION,
        course=manifest.course_version,
        law=law_version(library, manifest.law.amended_by),
        locales=manifest.locales,
        reference_locale=manifest.reference_locale,
        acts=[
            ActInfo(
                id=act.id,
                short_name=act.short_name,
                version=act.version,
                articles=len(act.articles),
            )
            for act in library.acts.values()
        ],
    )
