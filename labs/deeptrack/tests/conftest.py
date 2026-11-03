"""Shared fixtures: scripted turns and a sink that keeps every frame."""

from datetime import date

import pytest
from langchain_core.messages import AIMessage

from processors.models import RunEvent
from tests.support.fake import call

PROPOSAL = {"poliza": "pol-1001", "cobertura": "cob-rc", "fecha_ocurrencia": date(2026, 7, 1).isoformat()}


@pytest.fixture
def frames() -> list[RunEvent]:
    """Every frame a sink received, in arrival order."""
    return []


@pytest.fixture
def proposing() -> tuple[AIMessage, ...]:
    """Orchestrator delegates, the transactions subagent proposes a claim and reports, the orchestrator answers."""
    return (
        call("task", "t1", subagent_type="transacciones", description="Denunciar RC en pol-1001 el 2026-07-01"),
        call("proponer_denuncia", "p1", **PROPOSAL),
        AIMessage("Propuesta registrada."),
        AIMessage("He preparado la denuncia; queda pendiente de validación y aprobación."),
    )
