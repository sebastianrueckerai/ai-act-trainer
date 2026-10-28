from fastapi import APIRouter, Request, Response

from app.api.models import ThemeResponse

router = APIRouter(prefix="/api/theme", tags=["theme"])


@router.get("", response_model=ThemeResponse)
def get_theme(request: Request, response: Response) -> ThemeResponse:
    settings = request.app.state.settings
    response.headers["Cache-Control"] = "public, max-age=300"
    return ThemeResponse(
        primary=settings.theme_primary,
        secondary=settings.theme_secondary,
        accent=settings.theme_accent,
        background=settings.theme_background,
        look=settings.theme_look,
    )
