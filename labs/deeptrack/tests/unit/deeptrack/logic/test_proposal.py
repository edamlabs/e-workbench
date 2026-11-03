"""The proposing tools: a valid proposal lands in the state; a bad one is an error the model reads, never a crash."""

from typing import Any

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.types import Command

from deeptrack.logic.proposal import ProposalMiddleware

TOOLS = {tool.name: tool for tool in ProposalMiddleware().tools}


async def invoke(tool: BaseTool, **args: Any) -> Command | ToolMessage:
    """Call a tool the way the agent does: as a tool call, so the call id is injected."""
    return await tool.ainvoke({"type": "tool_call", "name": tool.name, "args": args, "id": "call-1"})


async def test_proposal_denuncia_lands_in_state() -> None:
    done = await invoke(
        TOOLS["proponer_denuncia"], poliza="pol-1001", cobertura="cob-rc", fecha_ocurrencia="2026-07-01"
    )
    assert isinstance(done, Command)
    assert done.update["propuesta"] == {
        "type": "denuncia",
        "poliza": "pol-1001",
        "cobertura": "cob-rc",
        "fecha_ocurrencia": "2026-07-01",
    }
    assert done.update["messages"][0].tool_call_id == "call-1"


async def test_proposal_endoso_lands_in_state() -> None:
    done = await invoke(TOOLS["proponer_endoso"], poliza="pol-1001", quita="cob-robo")
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
async def test_proposal_bad_names_reach_the_model(tool: str, args: dict[str, Any]) -> None:
    answer = await invoke(TOOLS[tool], **args)
    assert isinstance(answer, ToolMessage)
    assert answer.status == "error"
    assert "nombres locales" in answer.text
