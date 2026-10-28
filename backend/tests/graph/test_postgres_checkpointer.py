"""The graph advances across a phase boundary on a real AsyncPostgresSaver.

The unit tests feed strings directly; this one runs the graph on the real
substrate, so whatever the saver hands back after a checkpoint round-trip, the
graph still advances (the b3c8cd7 defect class: top-level enum channels
returning as plain strings).

The test writes real rows into the database named by TEST_POSTGRES_URL; the
target must be disposable. Against the compose stack, where the postgres
container has no host port, resolve the container IP first:

    docker inspect ai-act-trainer-postgres \
        --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'

The password is POSTGRES_PASSWORD in the repo .env. Then, from backend/:

    TEST_POSTGRES_URL=postgresql://trainer:<password>@<ip>:5432/trainer \
        uv run pytest tests/graph/test_postgres_checkpointer.py

docker compose down -v wipes the rows.
"""

import asyncio
import os
import uuid

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.graph.graph import build_graph
from app.graph.state import Phase, initial_state
from app.graph.triage import Triage

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRES_URL"),
    reason="TEST_POSTGRES_URL must name a disposable postgres",
)


def test_two_turns_on_one_thread_advance_the_lesson(make_deps):
    async def run():
        # Not open_checkpointer: under pytest settings.env is "test" and it
        # yields an InMemorySaver.
        url = os.environ["TEST_POSTGRES_URL"]
        async with AsyncPostgresSaver.from_conn_string(url) as saver:
            await saver.setup()
            deps = make_deps(
                script={
                    "triage": [
                        Triage(guard="ok", intent="continue"),
                        Triage(guard="ok", intent="continue"),
                    ],
                    "persona": "<echo>",
                }
            )
            graph = build_graph(deps, saver)
            config = {"configurable": {"thread_id": f"pg-{uuid.uuid4().hex}"}}
            first = await graph.ainvoke(
                initial_state("clerk") | {"messages": [HumanMessage("Hallo")]}, config
            )
            second = await graph.ainvoke({"messages": [HumanMessage("weiter")]}, config)
            return first, second

    first, second = asyncio.run(run())

    assert isinstance(first["messages"][-1], AIMessage)
    assert first["phase"] is Phase.lesson
    assert first["persona_id"] == "clerk"
    assert first["step_idx"] == 1

    assert isinstance(second["messages"][-1], AIMessage)
    assert second["phase"] is Phase.lesson
    assert second["step_idx"] == 2
