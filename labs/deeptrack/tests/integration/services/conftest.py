"""Fixtures of the services tier on the stack: the scripted claim and the MCP calls the gate makes."""

from collections.abc import Callable

import pytest
from langchain_core.messages import AIMessage

from tests.support.fake import call

type Claim = Callable[[str, str], tuple[AIMessage, ...]]


@pytest.fixture
def gate_calls() -> list[str]:
    """The MCP calls the gate makes for one proposal, in order."""
    return ["onto_clear", "onto_load", "onto_load", "onto_load", "onto_shacl"]


@pytest.fixture
def claim() -> Claim:
    """`claim(poliza, fecha)`: the scripted turn proposing a claim on `poliza` dated `fecha`, then a closing answer."""

    def scripted(poliza: str, fecha: str) -> tuple[AIMessage, ...]:
        return (
            call("task", "t1", subagent_type="transacciones", description=f"Denunciar RC en {poliza}"),
            call("proponer_denuncia", "p1", poliza=poliza, cobertura="cob-rc", fecha_ocurrencia=fecha),
            AIMessage("Propuesta registrada."),
            AIMessage("Propuesta enviada a validación."),
            AIMessage("No procede: la fecha cae fuera de la vigencia."),
        )

    return scripted
