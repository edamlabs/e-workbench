"""The gate's verdicts: none to judge, conforming, violating, and the retry cap."""

from typing import Any

from logic.gate import RETRIES
from logic.state import ChatState
from tests.unit.logic.conftest import Gate


async def test_gate_without_proposal_ends(gate: Gate) -> None:
    state: ChatState = {"messages": []}
    assert (await gate().run(state, {})).goto == "__end__"


async def test_gate_conforming_goes_to_approval(gate: Gate, denuncia: dict[str, Any]) -> None:
    state: ChatState = {"messages": [], "propuesta": denuncia}
    verdict = await gate(True).run(state, {})
    assert verdict.goto == "approval"
    assert verdict.update == {"errores": [], "intentos": 0}


async def test_gate_violation_returns_with_report(gate: Gate, denuncia: dict[str, Any]) -> None:
    state: ChatState = {"messages": [], "propuesta": denuncia}
    verdict = await gate(False).run(state, {})
    assert verdict.goto == "agent"
    assert verdict.update["intentos"] == 1
    assert "fuera de vigencia" in verdict.update["messages"][0].text


async def test_gate_retry_cap_closes_turn(gate: Gate, denuncia: dict[str, Any]) -> None:
    state: ChatState = {"messages": [], "propuesta": denuncia, "intentos": RETRIES - 1}
    verdict = await gate(False).run(state, {})
    assert verdict.goto == "__end__"
    assert verdict.update["propuesta"] is None
