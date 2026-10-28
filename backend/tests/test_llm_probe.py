import httpx

from app.llm.probe import probe_llm
from app.settings import Settings


def make_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_probe_reports_models_when_reachable():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        assert request.headers["authorization"] == "Bearer sk-test"
        return httpx.Response(200, json={"data": [{"id": "strong"}, {"id": "fast"}]})

    settings = Settings(_env_file=None, llm_base_url="http://llm/v1", llm_api_key="sk-test")
    probe = probe_llm(settings, client=make_client(handler))
    assert probe.reachable is True
    assert probe.models == ["strong", "fast"]
    assert probe.error is None


def test_probe_reports_error_when_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    settings = Settings(_env_file=None, llm_base_url="http://llm/v1")
    probe = probe_llm(settings, client=make_client(handler))
    assert probe.reachable is False
    assert probe.models == []
    assert probe.error == "unreachable"


def test_probe_reports_http_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"})

    settings = Settings(_env_file=None, llm_base_url="http://llm/v1")
    probe = probe_llm(settings, client=make_client(handler))
    assert probe.reachable is False
    assert "401" in probe.error


def test_probe_reports_non_json_body_as_malformed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>proxy error</html>")

    settings = Settings(_env_file=None, llm_base_url="http://llm/v1")
    probe = probe_llm(settings, client=make_client(handler))
    assert probe.reachable is False
    assert probe.models == []
    assert probe.error == "malformed response"


def test_probe_reports_items_without_id_as_malformed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"name": "no-id"}]})

    settings = Settings(_env_file=None, llm_base_url="http://llm/v1")
    probe = probe_llm(settings, client=make_client(handler))
    assert probe.reachable is False
    assert probe.error == "malformed response: no model ids"


def test_probe_reports_a_json_array_body_as_malformed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2])

    settings = Settings(_env_file=None, llm_base_url="http://llm/v1")
    probe = probe_llm(settings, client=make_client(handler))
    assert probe.reachable is False
    assert probe.models == []
    assert probe.error == "malformed response: body is not an object"


def test_llm_health_endpoint_uses_probe(client, monkeypatch):
    from app.api import health
    from app.llm.probe import LlmProbe

    monkeypatch.setattr(
        health,
        "probe_llm",
        lambda settings: LlmProbe(reachable=True, models=["strong"], error=None),
    )
    body = client.get("/api/health/llm").json()
    assert body == {"reachable": True, "models": ["strong"], "error": None}
