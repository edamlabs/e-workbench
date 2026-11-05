"""Shared fixtures: scripted turns and the real tree the stack-bound tiers run on."""

from collections.abc import AsyncIterator
from datetime import date

import pytest
from langchain_core.messages import AIMessage

from infra.lifespan.sealed import lifespan
from infra.state import State
from tests.support.fake import call

PROPOSAL = {"poliza": "pol-1001", "cobertura": "cob-rc", "fecha_ocurrencia": date(2026, 7, 1).isoformat()}


@pytest.fixture
def proposing() -> tuple[AIMessage, ...]:
    """Orchestrator delegates, the transactions subagent proposes a claim and reports, the orchestrator answers."""
    return (
        call("task", "t1", subagent_type="transacciones", description="Denunciar RC en pol-1001 el 2026-07-01"),
        call("proponer_denuncia", "p1", **PROPOSAL),
        AIMessage("Propuesta registrada."),
        AIMessage("He preparado la denuncia; queda pendiente de validación y aprobación."),
    )


@pytest.fixture
async def state() -> AsyncIterator[State]:
    """The real lifespan's sealed tree, opened for one test and closed after it."""
    async with lifespan() as tree:
        yield tree
