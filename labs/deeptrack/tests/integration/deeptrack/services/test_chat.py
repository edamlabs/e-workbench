"""ChatService over the real stack: the ontology servers judge, the projector sees MCP, Langfuse keeps the trace."""

import asyncio
import time

import httpx
import pytest
from langchain_core.messages import AIMessage

from deeptrack.lifespan.sealed import lifespan
from infra.settings import settings as st
from processors.models import EventKind, EventPhase, RunEvent
from tests.support.fake import FakeClassifier, ScriptedChat, call

pytestmark = pytest.mark.integration
GATE_CALLS = ["onto_clear", "onto_load", "onto_load", "onto_load", "onto_shacl"]


def claim(poliza: str, fecha: str) -> tuple[AIMessage, ...]:
    """The scripted turn proposing a claim on `poliza` dated `fecha`, then a closing answer."""
    return (
        call("task", "t1", subagent_type="transacciones", description=f"Denunciar RC en {poliza}"),
        call("proponer_denuncia", "p1", poliza=poliza, cobertura="cob-rc", fecha_ocurrencia=fecha),
        AIMessage("Propuesta registrada."),
        AIMessage("Propuesta enviada a validación."),
        AIMessage("No procede: la fecha cae fuera de la vigencia."),
    )


async def test_stack_conforming_claim_stops_for_approval(frames: list[RunEvent]) -> None:
    async with lifespan(classify=FakeClassifier(), chat=ScriptedChat(*claim("pol-1001", "2026-07-01"))) as state:
        turn = await state.services.chat.turn("it-ok", "denuncia RC pol-1001", frames.append)
    assert turn.interrupt is not None
    gate = next(frame.id for frame in frames if frame.name == "gate" and frame.phase is EventPhase.START)
    mcp = [frame.name for frame in frames if frame.kind is EventKind.MCP and frame.phase is EventPhase.START]
    assert mcp == GATE_CALLS
    assert all(frame.parent == gate for frame in frames if frame.kind is EventKind.MCP)


async def test_stack_out_of_term_claim_is_fed_back(frames: list[RunEvent]) -> None:
    async with lifespan(classify=FakeClassifier(), chat=ScriptedChat(*claim("pol-2002", "2026-07-01"))) as state:
        turn = await state.services.chat.turn("it-bad", "denuncia RC pol-2002", frames.append)
    assert turn.interrupt is None
    assert turn.reply.startswith("No procede")
    shacl = next(frame for frame in frames if frame.name == "onto_shacl" and frame.phase is EventPhase.END)
    assert "fuera de la vigencia" in shacl.payload["output"]


async def test_stack_trace_lands_in_langfuse(frames: list[RunEvent]) -> None:
    async with lifespan(classify=FakeClassifier(), chat=ScriptedChat(*claim("pol-1001", "2026-07-01"))) as state:
        turn = await state.services.chat.turn("it-trace", "denuncia RC pol-1001", frames.append)
        await state.providers.trace.flush()
    config = st.providers.drivers.trace.langfuse
    auth = (config.public_key, config.secret_key.get_secret_value())
    deadline = time.monotonic() + 45
    ### Langfuse v4 is observations-first: a trace is the observations sharing its id (Observations API v2).
    async with httpx.AsyncClient(base_url=config.url, auth=auth, params={"traceId": turn.trace_id}) as client:
        rows = (await client.get("/api/public/v2/observations")).json()["data"]
        while not rows and time.monotonic() < deadline:
            await asyncio.sleep(1)
            rows = (await client.get("/api/public/v2/observations")).json()["data"]
    names = {row["name"] for row in rows}
    assert {row["environment"] for row in rows} == {config.environment}
    assert {"agent", "gate", "approval", "task", "proponer_denuncia", "onto_shacl"} <= names
