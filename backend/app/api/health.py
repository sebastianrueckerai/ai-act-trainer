import structlog
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import text

from app.api.deps import get_settings_dep
from app.api.models import ReadyChecks, ReadyStatus, StatusResponse
from app.llm.probe import LlmProbe, probe_llm
from app.settings import Settings

router = APIRouter(prefix="/health", tags=["health"])

log = structlog.get_logger(__name__)


@router.get("/live")
def live() -> StatusResponse:
    return StatusResponse(status="ok")


@router.get("/ready")
def ready(request: Request, response: Response) -> ReadyStatus:
    checks = ReadyChecks(
        startup=bool(getattr(request.app.state, "ready", False)),
        database=False,
        content=hasattr(request.app.state, "content"),
    )
    engine = getattr(request.app.state, "engine", None)
    if engine is not None:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            checks.database = True
        except Exception as exc:  # noqa: BLE001 - a probe reports, it does not raise
            log.warning("database probe failed", error=str(exc))
            checks.database_error = "database unavailable"
    ok = checks.startup and checks.database and checks.content
    response.status_code = 200 if ok else 503
    return ReadyStatus(status="ready" if ok else "not-ready", checks=checks)


@router.get("/llm")
def llm(settings: Settings = Depends(get_settings_dep)) -> LlmProbe:
    return probe_llm(settings)
