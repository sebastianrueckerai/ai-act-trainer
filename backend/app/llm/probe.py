import httpx
import structlog
from pydantic import BaseModel

from app.settings import Settings

log = structlog.get_logger(__name__)


class LlmProbe(BaseModel):
    reachable: bool
    models: list[str]
    error: str | None


def probe_llm(settings: Settings, client: httpx.Client | None = None) -> LlmProbe:
    own_client = client is None
    client = client or httpx.Client(timeout=5.0)
    try:
        response = client.get(
            settings.llm_base_url.rstrip("/") + "/models",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        )
        if response.status_code != 200:
            return LlmProbe(reachable=False, models=[], error=f"HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            log.warning("llm probe returned a malformed body", error=str(exc))
            return LlmProbe(reachable=False, models=[], error="malformed response")
        if not isinstance(payload, dict):
            return LlmProbe(
                reachable=False, models=[], error="malformed response: body is not an object"
            )
        try:
            models = [item["id"] for item in payload.get("data", [])]
        except (ValueError, KeyError, TypeError):
            return LlmProbe(reachable=False, models=[], error="malformed response: no model ids")
        return LlmProbe(reachable=True, models=models, error=None)
    except httpx.HTTPError as exc:
        log.warning("llm probe failed", error=f"{type(exc).__name__}: {exc}")
        return LlmProbe(reachable=False, models=[], error="unreachable")
    finally:
        if own_client:
            client.close()
