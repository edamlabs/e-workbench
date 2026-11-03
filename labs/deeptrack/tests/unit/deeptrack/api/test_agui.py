"""POST /agui end to end over a scripted graph: the AG-UI stream, the interrupt, and its resume from the UI."""

import json
from typing import Any

from langchain_core.messages import AIMessage
from litestar import Litestar
from litestar.testing import AsyncTestClient

from deeptrack.api.agui import agui
from deeptrack.services.chat import ChatService
from deeptrack.state import ServicesState
from infra.state import State
from tests.support.fake import FakeTrace


def app_over(graph) -> Litestar:
    """The AG-UI route over a tree holding one chat service — no providers, no network."""
    app = Litestar(route_handlers=[agui])
    app.state.deeptrack = State(services=ServicesState(chat=ChatService(graph, FakeTrace(), frozenset())))
    return app


def run_input(thread: str, text: str, **forwarded: Any) -> dict[str, Any]:
    """A RunAgentInput as CopilotKit sends it."""
    return {
        "threadId": thread,
        "runId": "r1",
        "state": {},
        "messages": [{"id": "m1", "role": "user", "content": text}],
        "tools": [],
        "context": [],
        "forwardedProps": forwarded,
    }


async def events(client: AsyncTestClient, body: dict[str, Any]) -> list[dict[str, Any]]:
    """The decoded SSE events of one run."""
    response = await client.post("/agui", json=body, headers={"accept": "text/event-stream"})
    assert response.status_code == 201
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def kinds(stream: list[dict[str, Any]]) -> list[str]:
    return [event["type"] for event in stream]


async def test_agui_answer_streams(compiled) -> None:
    async with AsyncTestClient(app_over(compiled((), AIMessage("Cubre RC y robo.")))) as client:
        stream = await events(client, run_input("t1", "¿qué cubre pol-1001?"))
    assert kinds(stream)[0] == "RUN_STARTED"
    assert kinds(stream)[-1] == "RUN_FINISHED"
    assert "RUN_ERROR" not in kinds(stream)
    snapshot = [event for event in stream if event["type"] == "MESSAGES_SNAPSHOT"][-1]
    assert snapshot["messages"][-1]["content"] == "Cubre RC y robo."


async def test_agui_interrupt_then_approve(compiled, proposing) -> None:
    async with AsyncTestClient(app_over(compiled((True,), *proposing))) as client:
        stopped = await events(client, run_input("t2", "denuncia RC pol-1001"))
        interrupt = next(event for event in stopped if event["type"] == "CUSTOM" and event["name"] == "on_interrupt")
        assert json.loads(interrupt["value"])["propuesta"]["cobertura"] == "cob-rc"
        resumed = await events(
            client, run_input("t2", "denuncia RC pol-1001", command={"resume": {"decision": "aprobar"}})
        )
    assert "RUN_ERROR" not in kinds(resumed)
    snapshot = [event for event in resumed if event["type"] == "MESSAGES_SNAPSHOT"][-1]
    assert snapshot["messages"][-1]["content"].startswith("Transacción registrada")


async def test_agui_interrupt_then_reject(compiled, proposing) -> None:
    graph = compiled((True,), *proposing, AIMessage("Entendido: no se registra."))
    async with AsyncTestClient(app_over(graph)) as client:
        await events(client, run_input("t3", "denuncia RC pol-1001"))
        resumed = await events(
            client, run_input("t3", "denuncia RC pol-1001", command={"resume": {"decision": "rechazar"}})
        )
    snapshot = [event for event in resumed if event["type"] == "MESSAGES_SNAPSHOT"][-1]
    assert snapshot["messages"][-1]["content"] == "Entendido: no se registra."
