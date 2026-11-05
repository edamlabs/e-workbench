"""The proposing tools: a valid proposal lands in the state; a bad one is an error the model reads, never a crash."""

from typing import Any

import pytest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from tests.unit.logic.middleware.conftest import Invoke, Tools, Validated


async def test_proposal_denuncia_lands_in_state(tools: Tools, invoke: Invoke) -> None:
    done = await invoke(
        tools["proponer_denuncia"], poliza="pol-1001", cobertura="cob-rc", fecha_ocurrencia="2026-07-01"
    )
    assert isinstance(done, Command)
    assert done.update["propuesta"] == {
        "type": "denuncia",
        "poliza": "pol-1001",
        "cobertura": "cob-rc",
        "fecha_ocurrencia": "2026-07-01",
    }
    assert done.update["messages"][0].tool_call_id == "call-1"


async def test_proposal_endoso_lands_in_state(tools: Tools, invoke: Invoke) -> None:
    done = await invoke(tools["proponer_endoso"], poliza="pol-1001", quita="cob-robo")
    assert isinstance(done, Command)
    assert done.update["propuesta"] == {"type": "endoso", "poliza": "pol-1001", "quita": "cob-robo"}


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        (
            "proponer_denuncia",
            {"poliza": "pol-1001", "cobertura": "responsabilidad civil", "fecha_ocurrencia": "2026-07-01"},
        ),
        ("proponer_denuncia", {"poliza": "POL-1001", "cobertura": "cob-rc", "fecha_ocurrencia": "2026-07-01"}),
        ("proponer_endoso", {"poliza": "pol-1001", "quita": "Robo total"}),
    ],
    ids=["label-not-name", "uppercase", "endoso-label"],
)
async def test_proposal_bad_names_reach_the_model(
    tools: Tools, invoke: Invoke, tool: str, args: dict[str, Any]
) -> None:
    answer = await invoke(tools[tool], **args)
    assert isinstance(answer, ToolMessage)
    assert answer.status == "error"
    assert "nombres locales" in answer.text


async def test_proposal_prevalidated_conforming_lands(validated: Validated, invoke: Invoke) -> None:
    done = await invoke(validated(True)["proponer_endoso"], poliza="pol-1001", quita="cob-rc")
    assert isinstance(done, Command)
    assert done.update["propuesta"]["quita"] == "cob-rc"


async def test_proposal_prevalidated_violation_reaches_the_model(validated: Validated, invoke: Invoke) -> None:
    answer = await invoke(validated(False)["proponer_endoso"], poliza="pol-1001", quita="cob-robo")
    assert isinstance(answer, ToolMessage)
    assert answer.status == "error"
    assert "fuera de vigencia" in answer.text
