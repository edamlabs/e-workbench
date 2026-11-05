"""ChatService over the real stack: the ontology servers judge, the projector sees MCP, Langfuse keeps the trace."""

import asyncio
import time

import httpx
import pytest
from etrack.models.event import EventKind, EventPhase

from infra.lifespan.sealed import lifespan
from infra.settings import settings as st
from tests.integration.services.conftest import Claim
from tests.support.fake import FakeClassifier, ScriptedChat
from tests.support.track import record

pytestmark = pytest.mark.integration


async def test_stack_conforming_claim_stops_for_approval(claim: Claim, gate_calls: list[str]) -> None:
    async with lifespan(classify=FakeClassifier(), chat=ScriptedChat(*claim("pol-1001", "2026-07-01"))) as state:
        recorder = record(state.providers.track.bus)
        turn = await state.services.chat.turn("it-ok", "denuncia RC pol-1001")
        frames = await recorder.settled(turn.run_id)
    assert turn.interrupt is not None
    gate = next(frame.id for frame in frames if frame.name == "gate" and frame.phase is EventPhase.START)
    mcp = [frame.name for frame in frames if frame.kind is EventKind.MCP and frame.phase is EventPhase.START]
    assert mcp == gate_calls
    assert all(frame.parent == gate for frame in frames if frame.kind is EventKind.MCP)


async def test_stack_out_of_term_claim_is_fed_back(claim: Claim) -> None:
    async with lifespan(classify=FakeClassifier(), chat=ScriptedChat(*claim("pol-2002", "2026-07-01"))) as state:
        recorder = record(state.providers.track.bus)
        turn = await state.services.chat.turn("it-bad", "denuncia RC pol-2002")
        frames = await recorder.settled(turn.run_id)
    assert turn.interrupt is None
    assert turn.reply.startswith("No procede")
    shacl = next(frame for frame in frames if frame.name == "onto_shacl" and frame.phase is EventPhase.END)
    assert "fuera de la vigencia" in shacl.payload["output"]


async def test_stack_trace_lands_in_langfuse(claim: Claim) -> None:
    async with lifespan(classify=FakeClassifier(), chat=ScriptedChat(*claim("pol-1001", "2026-07-01"))) as state:
        recorder = record(state.providers.track.bus)
        turn = await state.services.chat.turn("it-trace", "denuncia RC pol-1001")
        await recorder.settled(turn.run_id)
        versions = {name: agent.version for name, agent in state.providers.harness.roster.agents.items()}
    ### leaving the lifespan drains the bus into the OTLP sink and shuts it down: every span is exported.
    auth = (st.LABS_LANGFUSE_PUBLIC_KEY, st.LABS_LANGFUSE_SECRET_KEY.get_secret_value())
    deadline = time.monotonic() + 45
    ### Langfuse v4 is observations-first: a trace is the observations sharing its id (Observations API v2).
    async with httpx.AsyncClient(
        base_url=st.langfuse_url, auth=auth, params={"traceId": turn.trace_id, "fields": "core,basic,metadata"}
    ) as client:
        rows = (await client.get("/api/public/v2/observations")).json()["data"]
        while not rows and time.monotonic() < deadline:
            await asyncio.sleep(1)
            rows = (await client.get("/api/public/v2/observations")).json()["data"]
    names = {row["name"] for row in rows}
    assert {row["environment"] for row in rows} == {st.LABS_LANGFUSE_ENVIRONMENT}
    assert {"agent", "gate", "approval", "transacciones", "proponer_denuncia", "onto_shacl"} <= names
    ### the agents' versions ride the run's root span: the trace names exactly what produced it.
    (root,) = [row for row in rows if row["isRootObservation"]]
    assert root["metadata"]["attributes.app.agents"] == versions
