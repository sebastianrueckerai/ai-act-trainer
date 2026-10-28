from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.deps import current_principal
from app.auth.identity import Principal
from app.graph.stage import SCENE, SCENE_LIGHT, persona_image_url

router = APIRouter(prefix="/api/personas", tags=["personas"])


class PersonaOut(BaseModel):
    id: str
    name: dict[str, str]
    tagline: dict[str, str]
    images: dict[str, str]
    scene: str | None = None


def _image_url(persona_id: str, emotion: str) -> str:
    return f"/api/personas/{persona_id}/images/{emotion}"


def _existing_images(request: Request, persona_id: str, emotions: list[str]) -> dict[str, str]:
    image_dir = request.app.state.settings.personas_dir / persona_id / "images"
    return {
        emotion: _image_url(persona_id, emotion)
        for emotion in emotions
        if (image_dir / f"{emotion}.png").is_file()
    }


@router.get("", response_model=list[PersonaOut])
def list_personas(
    request: Request, principal: Principal = Depends(current_principal)
) -> list[PersonaOut]:
    return [
        PersonaOut(
            id=persona.id,
            name=persona.name,
            tagline=persona.tagline,
            images=_existing_images(request, persona.id, persona.emotions),
            scene=persona_image_url(request.app.state.settings.personas_dir, persona.id, SCENE),
        )
        for persona in request.app.state.content.personas.values()
    ]


@router.get("/{persona_id}/images/{emotion}")
def get_persona_image(
    persona_id: str,
    emotion: str,
    request: Request,
    principal: Principal = Depends(current_principal),
) -> FileResponse:
    persona = request.app.state.content.personas.get(persona_id)
    if persona is None or emotion not in (*persona.emotions, SCENE, SCENE_LIGHT):
        raise HTTPException(status_code=404)
    path = request.app.state.settings.personas_dir / persona_id / "images" / f"{emotion}.png"
    if not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )
