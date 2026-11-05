"""The UI's path on the real model: the real app (lifespan, Gemini, stack) driven over AG-UI as CopilotKit does."""

import json
import time

import pytest
from litestar.testing import AsyncTestClient

from api.app import app
from tests.integration.api.conftest import Events, Reading, RunInput

pytestmark = [pytest.mark.integration, pytest.mark.llm]


async def test_agui_policy_read_arrives_whole(
    run_input: RunInput, events: Events, last_reply: Reading, streamed: Reading
) -> None:
    async with AsyncTestClient(app) as client:
        stream = await events(
            client,
            run_input(
                f"ui-q1-{time.time_ns()}", "¿Qué coberturas tiene la póliza pol-1001 y tiene siniestros abiertos?"
            ),
        )
    assert [event["message"] for event in stream if event["type"] == "RUN_ERROR"] == []
    reply = last_reply(stream)
    assert "sin-0001" in reply
    ### the cut-reply bug: what the UI typed must be the whole message the state holds.
    assert streamed(stream) == reply


async def test_agui_claim_interrupt_then_approve(run_input: RunInput, events: Events, last_reply: Reading) -> None:
    thread = f"ui-q3-{time.time_ns()}"
    question = "Quiero denunciar un siniestro de responsabilidad civil en la póliza pol-1001 ocurrido el 2026-07-01"
    async with AsyncTestClient(app) as client:
        stopped = await events(client, run_input(thread, question))
        interrupts = [json.loads(e["value"]) for e in stopped if e["type"] == "CUSTOM" and e["name"] == "on_interrupt"]
        assert [event["message"] for event in stopped if event["type"] == "RUN_ERROR"] == []
        assert interrupts[-1]["propuesta"]["cobertura"] == "cob-rc"
        resumed = await events(client, run_input(thread, question, command={"resume": {"decision": "aprobar"}}))
    assert [event["message"] for event in resumed if event["type"] == "RUN_ERROR"] == []
    assert last_reply(resumed).startswith("Transacción registrada")
