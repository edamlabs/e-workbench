"""PREGUNTAS.md on the real model and the real stack: structural assertions only — never the model's wording.

Each question asserts what must hold whatever the model says: which subagents, tools and MCP calls ran, what the
SHACL gate decided, whether the run stopped for approval, and that personal data never left masked. Where a
correct outcome has two paths (the agent refuses on its own, or the gate refuses it), the invariant is the
business one — nothing was asked to approve, nothing executed — and the path taken is reported."""

import asyncio
import json
import time

import httpx
import pytest
from etrack.models.event import EventKind

from infra.settings import settings as st
from infra.state import State
from models.proposal import Decision
from tests.integration.conftest import Conversation
from tests.support.track import exported

pytestmark = [pytest.mark.integration, pytest.mark.llm]


async def test_q1_policy_read(talk: Conversation) -> None:
    turn = await talk.say("¿Qué coberturas tiene la póliza pol-1001 y tiene siniestros abiertos?")
    assert talk.crashed() == []
    assert talk.started(EventKind.TOOL, "consultar_poliza")
    assert talk.started(EventKind.MCP, "onto_query")
    assert turn.interrupt is None
    assert "sin-0001" in turn.reply


async def test_q2_ontology_relations(talk: Conversation) -> None:
    turn = await talk.say("¿Cómo se relaciona un siniestro con una póliza y qué atributos tiene un endoso?")
    assert talk.crashed() == []
    assert talk.delegated("ontologo")
    assert talk.started(EventKind.MCP, "onto_query")
    assert turn.interrupt is None


async def test_q3_valid_claim_approved(talk: Conversation, executed: str) -> None:
    stopped = await talk.say(
        "Quiero denunciar un siniestro de responsabilidad civil en la póliza pol-1001 ocurrido el 2026-07-01"
    )
    assert talk.crashed() == []
    assert stopped.interrupt is not None
    assert stopped.interrupt["propuesta"] == {
        "type": "denuncia",
        "poliza": "pol-1001",
        "cobertura": "cob-rc",
        "fecha_ocurrencia": "2026-07-01",
    }
    assert '"conforms":true' in talk.ended("onto_shacl")[-1].payload["output"].replace(" ", "")
    done = await talk.say(Decision.APROBAR)
    assert done.interrupt is None
    assert done.reply.startswith(executed)


async def test_q4_valid_claim_rejected(talk: Conversation, executed: str) -> None:
    stopped = await talk.say(
        "Quiero denunciar un siniestro de responsabilidad civil en la póliza pol-1001 ocurrido el 2026-07-02"
    )
    assert stopped.interrupt is not None
    done = await talk.say(Decision.RECHAZAR)
    assert talk.crashed() == []
    assert done.interrupt is None
    assert executed not in done.reply


@pytest.mark.parametrize(
    ("question", "violation"),
    [
        ("Denuncia un incendio en la póliza pol-2002 ocurrido el 2026-07-01", "fuera de la vigencia"),
        ("Quita la cobertura de robo total de la póliza pol-1001", "siniestro abierto"),
    ],
    ids=["q5-out-of-term", "q6-endorsement-open-claim"],
)
async def test_q5_q6_invalid_never_reaches_approval(
    talk: Conversation, executed: str, question: str, violation: str, record_property
) -> None:
    turn = await talk.say(question)
    assert talk.crashed() == []
    assert turn.interrupt is None
    assert all(executed not in each.reply for each in talk.turns)
    verdicts = [frame.payload.get("output", "") for frame in talk.ended("onto_shacl")]
    proposed = talk.started(EventKind.TOOL, "proponer_denuncia") + talk.started(EventKind.TOOL, "proponer_endoso")
    ### who stopped it: the gate (a proposal judged and refused) or the agent (no proposal at all).
    stopper = "gate" if proposed else "agent"
    record_property("stopped_by", stopper)
    assert stopper == "agent" or any(violation in verdict for verdict in verdicts)


async def test_q7_personal_data_masked(talk: Conversation, state: State) -> None:
    turn = await talk.say("El asegurado con CUIT 20-11111111-2 pregunta qué cubre su póliza pol-1001")
    assert talk.crashed() == []
    raw = ("20-11111111-2", "20111111112")
    assert not any(cuit in json.dumps(frame.payload, ensure_ascii=False) for frame in talk.frames for cuit in raw)
    await exported(state)
    auth = (st.LABS_LANGFUSE_PUBLIC_KEY, st.LABS_LANGFUSE_SECRET_KEY.get_secret_value())
    async with httpx.AsyncClient(
        base_url=st.langfuse_url, auth=auth, params={"traceId": turn.trace_id, "fields": "core,basic,io"}
    ) as client:
        rows = (await client.get("/api/public/v2/observations")).json()["data"]
        deadline = time.monotonic() + 30
        while not rows and time.monotonic() < deadline:
            await asyncio.sleep(1)
            rows = (await client.get("/api/public/v2/observations")).json()["data"]
    stored = json.dumps(rows, ensure_ascii=False)
    assert rows
    assert not any(cuit in stored for cuit in raw)
    assert "[CUIT]" in stored
