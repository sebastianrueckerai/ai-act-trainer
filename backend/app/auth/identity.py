from typing import Protocol

from fastapi import APIRouter
from pydantic import BaseModel

GUEST_PREFIX = "guest-"


class Principal(BaseModel):
    subject: str
    name: str
    email: str | None = None
    groups: list[str] = []
    roles: list[str] = []


class Identity(Protocol):
    name: str

    def router(self) -> APIRouter: ...


def assign_roles(groups: list[str], admin_groups: list[str]) -> list[str]:
    roles = ["student"]
    if set(groups) & set(admin_groups):
        roles.append("admin")
    return roles


def is_guest(principal: Principal) -> bool:
    return principal.subject.startswith(GUEST_PREFIX)
