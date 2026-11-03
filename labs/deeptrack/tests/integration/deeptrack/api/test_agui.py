"""The UI's path on the real model: the real app (lifespan, Gemini, stack) driven over AG-UI as CopilotKit does."""

import json
import time
from typing import Any

import pytest
from litestar.testing import AsyncTestClient

from deeptrack.api.app import app

pytestmark = [pytest.mark.integration, pytest.mark.llm]


def run_input(thread: str, text: str, **forwarded: Any) -> dict[str, Any]:
    return {
        "threadId": thread,
        "runId": f"r-{time.time_ns()}",
        "state": {},
        "messages": [{"id": "m1", "role": "user", "content": text}],
        "tools": [],
        "context": [],
        "forwardedProps": forwarded,
    }


async def events(client: AsyncTestClient, body: dict[str, Any]) -> list[dict[str, Any]]:
    response = await client.post("/agui", json=body, headers={"accept": "text/event-stream"}, timeout=180)
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def last_reply(stream: list[dict[str, Any]]) -> str:
    snapshot = [event for event in stream if event["type"] == "MESSAGES_SNAPSHOT"][-1]
    return str(snapshot["messages"][-1].get("content", ""))


def streamed(stream: list[dict[str, Any]]) -> str:
    """The text the UI typed, delta by delta, for the last assistant message."""
    ends = [event["messageId"] for event in stream if event["type"] == "TEXT_MESSAGE_END"]
    return "".join(e["delta"] for e in stream if e["type"] == "TEXT_MESSAGE_CONTENT" and e["messageId"] == ends[-1])


async def test_agui_policy_read_arrives_whole() -> None:
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


async def test_agui_claim_interrupt_then_approve() -> None:
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
