import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.content.loader import load_content
from app.corpus.search import SearchIndex
from tests.conftest import REPO_ROOT
from tests.fakes.scripted import ScriptedChatModel


@pytest.fixture(scope="module")
def content():
    return load_content(REPO_ROOT / "content", REPO_ROOT / "personas")


@pytest.fixture(scope="module")
def search_index(library):
    return SearchIndex.build(library)


@pytest.fixture
def make_deps(settings, library, content, search_index):
    from app.graph.deps import GraphDeps

    def _make(
        script: dict | None = None, record: list | None = None, **setting_overrides
    ) -> GraphDeps:
        model = ScriptedChatModel(script=script or {})
        deps = GraphDeps(
            library=library,
            content=content,
            search=search_index,
            models={"strong": model, "fast": model},
            settings=settings.model_copy(update=setting_overrides)
            if setting_overrides
            else settings,
            law_version="test",
        )
        if record is not None:
            deps.record_completion = record.append
        return deps

    return _make


@pytest.fixture
def make_graph(make_deps):
    from app.graph.graph import build_graph

    def _make(script=None, record=None, checkpointer=None, deps=None):
        deps = deps if deps is not None else make_deps(script=script, record=record)
        return build_graph(deps, checkpointer if checkpointer is not None else InMemorySaver())

    return _make
