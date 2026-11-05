"""Fixtures of the api tier: the routes mounted over a hand-built state tree, and the AG-UI wire helpers."""

import json
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from etrack.logic.api import Tracker
from etrack.logic.viewer import Viewer
from etrack.ports.topology import Topology, TopologyNode
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from litestar import Litestar
from litestar.testing import AsyncTestClient

from api.agui import agui
from api.viewer import viewer
from infra.state import State
from services.chat import ChatService
from services.state import ServicesState
from tests.support.agents import READING, arms
from tests.support.fake import ToolOntology, script

type AguiOver = Callable[[CompiledStateGraph, Tracker[RunnableConfig]], Litestar]
type ViewerOver = Callable[[Viewer | None], Litestar]
type RunInput = Callable[..., dict[str, Any]]
type Events = Callable[[AsyncTestClient, dict[str, Any]], Awaitable[list[dict[str, Any]]]]
type Kinds = Callable[[list[dict[str, Any]]], list[str]]


@pytest.fixture
def agui_over() -> AguiOver:
    """`agui_over(graph, tracker)`: the AG-UI route over a tree holding one chat service — no providers, no network."""

    def built(graph: CompiledStateGraph, tracker: Tracker[RunnableConfig]) -> Litestar:
        app = Litestar(route_handlers=[agui])
        app.state.deeptrack = State(
            services=ServicesState(
                chat=ChatService(graph, tracker), arms=arms(script(), ToolOntology(READING)), viewer=None
            )
        )
        return app

    return built


@pytest.fixture
def viewer_over() -> ViewerOver:
    """`viewer_over(canvas)`: the mount over a tree holding the canvas only."""

    def built(canvas: Viewer | None) -> Litestar:
        app = Litestar(route_handlers=[viewer])
        app.state.deeptrack = State(services=State(viewer=canvas))
        return app

    return built


@pytest.fixture
def topology() -> Topology:
    """A topology of one entry node."""
    return Topology(nodes=(TopologyNode(id="agent", name="agent", entry=True),), edges=())


@pytest.fixture
def run_input() -> RunInput:
    """`run_input(thread, text, **forwarded)`: a RunAgentInput as CopilotKit sends it."""

    def built(thread: str, text: str, **forwarded: Any) -> dict[str, Any]:
        return {
            "threadId": thread,
            "runId": "r1",
            "state": {},
            "messages": [{"id": "m1", "role": "user", "content": text}],
            "tools": [],
            "context": [],
            "forwardedProps": forwarded,
        }

    return built


@pytest.fixture
def events() -> Events:
    """`await events(client, body)`: the decoded SSE events of one run."""

    async def posted(client: AsyncTestClient, body: dict[str, Any]) -> list[dict[str, Any]]:
        response = await client.post("/agui", json=body, headers={"accept": "text/event-stream"})
        assert response.status_code == 201
        return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]

    return posted


@pytest.fixture
def kinds() -> Kinds:
    """`kinds(stream)`: the event types of a stream, in order."""
    return lambda stream: [event["type"] for event in stream]
