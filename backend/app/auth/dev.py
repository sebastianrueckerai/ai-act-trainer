from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from app.api.models import DevUser, StatusResponse
from app.auth.identity import Principal, assign_roles
from app.auth.session import SessionCookie

DEV_USERS = [
    Principal(subject="demo", name="Demo", email="demo@example.org", groups=["staff"]),
    Principal(subject="anna", name="Anna Beispiel", email="anna@example.org", groups=["staff"]),
    Principal(
        subject="boris",
        name="Boris Muster",
        email="boris@example.org",
        groups=["staff", "compliance"],
    ),
]


class DevLogin(BaseModel):
    subject: str = Field(min_length=1)


class DevIdentity:
    name = "dev"

    def __init__(self, cookie: SessionCookie, admin_groups: list[str]) -> None:
        self.cookie = cookie
        self.admin_groups = admin_groups

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/auth/dev", tags=["auth"])

        @router.get("/users")
        def users() -> list[DevUser]:
            return [DevUser(subject=user.subject, name=user.name) for user in DEV_USERS]

        @router.post("/login")
        def login(body: DevLogin, response: Response) -> StatusResponse:
            match = next((user for user in DEV_USERS if user.subject == body.subject), None)
            base = match or Principal(subject=body.subject, name=body.subject)
            principal = base.model_copy(
                update={"roles": assign_roles(base.groups, self.admin_groups)}
            )
            self.cookie.set(response, principal)
            return StatusResponse(status="ok")

        return router
