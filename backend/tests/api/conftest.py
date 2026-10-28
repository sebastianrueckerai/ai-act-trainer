from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from app.graph.critic import Critique
from app.graph.deps import GraphDeps
from app.graph.graph import build_graph
from app.graph.triage import Triage
from app.main import create_app
from app.settings import Settings
from tests.fakes.proxy import ADMIN_KEY, BASE_URL, FakeProxy
from tests.fakes.scripted import ScriptedChatModel

# The first lesson turn from tests/graph/test_events.py: triage's structured
# verdict and the persona rewrite, nothing else.
SHIP = Critique(verdict="ship", score=5)
DEFAULT_SCRIPT = {
    "triage": Triage(guard="ok", intent="continue"),
    "persona": "<echo>",
    "critic": SHIP,
    "voice_critic": SHIP,
}


def install_script(app, script: dict) -> None:
    model = ScriptedChatModel(script=script)
    deps = GraphDeps(
        library=app.state.library,
        content=app.state.content,
        search=app.state.search,
        models={"strong": model, "fast": model},
        settings=app.state.settings,
        law_version="test",
    )
    app.state.graph = build_graph(deps, InMemorySaver())
    app.state.deps = deps


@pytest.fixture
def scripted_client(request, client):
    install_script(client.app, getattr(request, "param", DEFAULT_SCRIPT))
    return client


@pytest.fixture
def fake_proxy() -> FakeProxy:
    return FakeProxy()


@pytest.fixture
def budget_client(request, settings: Settings, fake_proxy: FakeProxy) -> Iterator[TestClient]:
    """The public demo's app: invited accounts, guests, budgets kept by a fake proxy."""
    budgets = settings.model_copy(
        update={
            "auth_backend": "invite",
            "guest_access": True,
            "litellm_admin_key": ADMIN_KEY,
            "llm_base_url": BASE_URL,
        }
    )
    app = create_app(budgets)
    with TestClient(app) as client:
        app.state.budget.close()
        app.state.budget = fake_proxy.client()
        install_script(app, getattr(request, "param", DEFAULT_SCRIPT))
        yield client
