"""The gate's verdicts: none to judge, conforming, violating, and the retry cap."""

from deeptrack.logic.gate import RETRIES, ShaclGate
from deeptrack.logic.state import ChatState
from engines.shacl import ShaclEngine
from tests.conftest import PROPOSAL
from tests.support.fake import FakeOntology

DENUNCIA = {"type": "denuncia", **PROPOSAL}


def gate(*verdicts: bool) -> ShaclGate:
    return ShaclGate(ShaclEngine(FakeOntology(verdicts), base=(), shapes="shapes"))


async def test_gate_without_proposal_ends() -> None:
    state: ChatState = {"messages": []}
    assert (await gate().run(state, {})).goto == "__end__"


async def test_gate_conforming_goes_to_approval() -> None:
    state: ChatState = {"messages": [], "propuesta": DENUNCIA}
    verdict = await gate(True).run(state, {})
    assert verdict.goto == "approval"
    assert verdict.update == {"errores": [], "intentos": 0}


async def test_gate_violation_returns_with_report() -> None:
    state: ChatState = {"messages": [], "propuesta": DENUNCIA}
    verdict = await gate(False).run(state, {})
    assert verdict.goto == "agent"
    assert verdict.update["intentos"] == 1
    assert "fuera de vigencia" in verdict.update["messages"][0].text


async def test_gate_retry_cap_closes_turn() -> None:
    state: ChatState = {"messages": [], "propuesta": DENUNCIA, "intentos": RETRIES - 1}
    verdict = await gate(False).run(state, {})
    assert verdict.goto == "__end__"
    assert verdict.update["propuesta"] is None
