import secrets

from fastapi import APIRouter, Request, Response

from app.api.models import AuthOptions, StatusResponse
from app.auth.identity import GUEST_PREFIX, Principal, assign_roles

router = APIRouter(prefix="/auth", tags=["auth"])
guest_router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/logout")
def logout(request: Request, response: Response) -> StatusResponse:
    request.app.state.session_cookie.clear(response)
    return StatusResponse(status="ok")


@router.get("/options")
def options(request: Request) -> AuthOptions:
    settings = request.app.state.settings
    return AuthOptions(backend=settings.auth_backend, guest=settings.guest_access)


@guest_router.post("/guest")
def guest(request: Request, response: Response) -> StatusResponse:
    """A fresh guest per press: their own session and thread, the pool's money."""
    groups = ["guest"]
    principal = Principal(
        subject=f"{GUEST_PREFIX}{secrets.token_urlsafe(16)}",
        name="Gast",
        groups=groups,
        roles=assign_roles(groups, request.app.state.settings.admin_groups),
    )
    request.app.state.session_cookie.set(response, principal)
    return StatusResponse(status="ok")
