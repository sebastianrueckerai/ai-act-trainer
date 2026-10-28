from fastapi import APIRouter, Depends

from app.api.deps import current_principal, get_settings_dep
from app.api.models import MeResponse
from app.auth.identity import Principal
from app.settings import Settings

router = APIRouter(tags=["me"])

STORED_BY_LEVEL = {
    0: ["pass_date", "course_version", "law_version", "locale", "persona"],
    1: ["attempts", "scores", "per_question_results"],
    2: ["transcripts", "taught_content"],
}


@router.get("/me")
def me(
    principal: Principal = Depends(current_principal),
    settings: Settings = Depends(get_settings_dep),
) -> MeResponse:
    stored = [item for level in range(settings.data_level + 1) for item in STORED_BY_LEVEL[level]]
    return MeResponse(principal=principal, data_level=settings.data_level, stored=stored)
