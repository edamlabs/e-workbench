"""Fixtures of the api tier on the real app: AG-UI run inputs and the readings of their event streams."""

import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from litestar.testing import AsyncTestClient

type RunInput = Callable[..., dict[str, Any]]
type Events = Callable[[AsyncTestClient, dict[str, Any]], Awaitable[list[dict[str, Any]]]]
type Reading = Callable[[list[dict[str, Any]]], str]


@pytest.fixture
def run_input() -> RunInput:
    """`run_input(thread, text, **forwarded)`: a RunAgentInput as CopilotKit sends it, with a fresh run id."""

    def built(thread: str, text: str, **forwarded: Any) -> dict[str, Any]:
        return {
            "threadId": thread,
            "runId": f"r-{time.time_ns()}",
            "state": {},
            "messages": [{"id": "m1", "role": "user", "content": text}],
            "tools": [],
            "context": [],
            "forwardedProps": forwarded,
        }

    return built


@pytest.fixture
def events() -> Events:
    """`await events(client, body)`: the decoded SSE events of one run on the real model."""

    async def posted(client: AsyncTestClient, body: dict[str, Any]) -> list[dict[str, Any]]:
        response = await client.post("/agui", json=body, headers={"accept": "text/event-stream"}, timeout=180)
        return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]

    return posted


@pytest.fixture
def last_reply() -> Reading:
    """`last_reply(stream)`: the content of the last assistant message in the final snapshot."""

    def read(stream: list[dict[str, Any]]) -> str:
        snapshot = [event for event in stream if event["type"] == "MESSAGES_SNAPSHOT"][-1]
        return str(snapshot["messages"][-1].get("content", ""))

    return read


@pytest.fixture
def streamed() -> Reading:
    """`streamed(stream)`: the text the UI typed, delta by delta, for the last assistant message."""

    def read(stream: list[dict[str, Any]]) -> str:
        ends = [event["messageId"] for event in stream if event["type"] == "TEXT_MESSAGE_END"]
        return "".join(e["delta"] for e in stream if e["type"] == "TEXT_MESSAGE_CONTENT" and e["messageId"] == ends[-1])

    return read
