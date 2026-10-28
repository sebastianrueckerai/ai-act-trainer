from collections.abc import Iterator

from fastapi import HTTPException, Request

from app.auth.identity import Principal
from app.settings import Settings
from app.storage.repository import Repository, SqlAlchemyRepository


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_repository(request: Request) -> Iterator[Repository]:
    with request.app.state.session_factory() as session:
        yield SqlAlchemyRepository(session)
        session.commit()


def current_principal(request: Request) -> Principal:
    principal = request.app.state.session_cookie.read(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="not signed in")
    return principal


def user_id(principal: Principal, repo: Repository) -> int:
    return repo.upsert_user(principal.subject, principal.name, principal.email, principal.groups).id
