from app.auth.dev import DevIdentity
from app.auth.identity import Identity
from app.auth.invite import InviteIdentity
from app.auth.session import SessionCookie
from app.settings import Settings


def build_session_cookie(settings: Settings) -> SessionCookie:
    return SessionCookie(
        settings.secret_key, settings.session_max_age_seconds, secure=settings.is_production
    )


def build_identity(settings: Settings, cookie: SessionCookie) -> Identity:
    if settings.auth_backend == "dev":
        return DevIdentity(cookie, settings.admin_groups)
    if settings.auth_backend == "invite":
        return InviteIdentity(cookie, settings.admin_groups)
    raise NotImplementedError(f"auth backend {settings.auth_backend} arrives in milestone M6")
