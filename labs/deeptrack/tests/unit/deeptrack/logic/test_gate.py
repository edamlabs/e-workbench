"""The gate's verdicts: none to judge, conforming, violating, and the retry cap."""

from langgraph.graph import END

from deeptrack.logic.gate import RETRIES, ShaclGate
from deeptrack.logic.state import ChatState
from tests.conftest import PROPOSAL
from tests.support.fake import FakeOnto

DENUNCIA = {"type": "denuncia", **PROPOSAL}


async def test_gate_without_proposal_ends() -> None:
    assert (await ShaclGate(FakeOnto()).run({"messages": []}, {})).goto == END


async def test_gate_conforming_goes_to_approval() -> None:
    verdict = await ShaclGate(FakeOnto([True])).run({"messages": [], "propuesta": DENUNCIA}, {})
    assert verdict.goto == "approval"
    assert verdict.update == {"errores": [], "intentos": 0}


async def test_gate_violation_returns_with_report() -> None:
    verdict = await ShaclGate(FakeOnto([False])).run({"messages": [], "propuesta": DENUNCIA}, {})
    assert verdict.goto == "agent"
    assert verdict.update["intentos"] == 1
    assert "fuera de vigencia" in verdict.update["messages"][0].text


async def test_gate_retry_cap_closes_turn() -> None:
    state: ChatState = {"messages": [], "propuesta": DENUNCIA, "intentos": RETRIES - 1}
    verdict = await ShaclGate(FakeOnto([False])).run(state, {})
    assert verdict.goto == END
    assert verdict.update["propuesta"] is None
