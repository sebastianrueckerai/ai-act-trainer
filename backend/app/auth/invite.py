import hashlib

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.api.deps import get_repository
from app.api.models import StatusResponse
from app.auth.identity import Principal, assign_roles
from app.auth.session import SessionCookie
from app.storage.repository import Repository


class InviteLogin(BaseModel):
    token: str = Field(min_length=1, max_length=128)


def invite_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class InviteIdentity:
    """Named accounts: the invite link's token is the password, until the account is revoked."""

    name = "invite"

    def __init__(self, cookie: SessionCookie, admin_groups: list[str]) -> None:
        self.cookie = cookie
        self.admin_groups = admin_groups

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/auth/invite", tags=["auth"])

        @router.post("/login")
        def login(
            body: InviteLogin, response: Response, repo: Repository = Depends(get_repository)
        ) -> StatusResponse:
            account = repo.account_by_invite_hash(invite_hash(body.token))
            if account is None or account.revoked_at is not None:
                raise HTTPException(status_code=401, detail="invite not valid")
            groups = ["account"]
            principal = Principal(
                subject=account.subject,
                name=account.name,
                groups=groups,
                roles=assign_roles(groups, self.admin_groups),
            )
            self.cookie.set(response, principal)
            return StatusResponse(status="ok")

        return router
