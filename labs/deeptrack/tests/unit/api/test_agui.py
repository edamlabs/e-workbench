"""POST /agui end to end over a scripted graph: the AG-UI stream, the interrupt, and its resume from the UI."""

import json

from langchain_core.messages import AIMessage
from litestar.testing import AsyncTestClient

from tests.support.track import tracked
from tests.unit.api.conftest import AguiOver, Events, Kinds, RunInput
from tests.unit.conftest import Compile


async def test_agui_answer_streams(
    compiled: Compile, agui_over: AguiOver, run_input: RunInput, events: Events, kinds: Kinds
) -> None:
    async with (
        tracked() as (tracker, _),
        AsyncTestClient(agui_over(compiled((), AIMessage("Cubre RC y robo.")), tracker)) as client,
    ):
        stream = await events(client, run_input("t1", "¿qué cubre pol-1001?"))
    assert kinds(stream)[0] == "RUN_STARTED"
    assert kinds(stream)[-1] == "RUN_FINISHED"
    assert "RUN_ERROR" not in kinds(stream)
    snapshot = [event for event in stream if event["type"] == "MESSAGES_SNAPSHOT"][-1]
    assert snapshot["messages"][-1]["content"] == "Cubre RC y robo."


async def test_agui_interrupt_then_approve(
    compiled: Compile,
    proposing: tuple[AIMessage, ...],
    *,
    agui_over: AguiOver,
    run_input: RunInput,
    events: Events,
    kinds: Kinds,
) -> None:
    async with (
        tracked() as (tracker, _),
        AsyncTestClient(agui_over(compiled((True,), *proposing), tracker)) as client,
    ):
        stopped = await events(client, run_input("t2", "denuncia RC pol-1001"))
        interrupt = next(event for event in stopped if event["type"] == "CUSTOM" and event["name"] == "on_interrupt")
        assert json.loads(interrupt["value"])["propuesta"]["cobertura"] == "cob-rc"
        resumed = await events(
            client, run_input("t2", "denuncia RC pol-1001", command={"resume": {"decision": "aprobar"}})
        )
    assert "RUN_ERROR" not in kinds(resumed)
    snapshot = [event for event in resumed if event["type"] == "MESSAGES_SNAPSHOT"][-1]
    assert snapshot["messages"][-1]["content"].startswith("Transacción registrada")


async def test_agui_interrupt_then_reject(
    compiled: Compile,
    proposing: tuple[AIMessage, ...],
    agui_over: AguiOver,
    run_input: RunInput,
    events: Events,
) -> None:
    graph = compiled((True,), *proposing, AIMessage("Entendido: no se registra."))
    async with tracked() as (tracker, _), AsyncTestClient(agui_over(graph, tracker)) as client:
        await events(client, run_input("t3", "denuncia RC pol-1001"))
        resumed = await events(
            client, run_input("t3", "denuncia RC pol-1001", command={"resume": {"decision": "rechazar"}})
        )
    snapshot = [event for event in resumed if event["type"] == "MESSAGES_SNAPSHOT"][-1]
    assert snapshot["messages"][-1]["content"] == "Entendido: no se registra."
