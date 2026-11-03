"""The agent's roles and tools: whitelists per role, and the policy reader's boundary."""

import pytest
from langchain_core.tools import ToolException

from deeptrack.logic.agent import InsuranceAgent
from tests.support.fake import FakeOntology, ToolOntology, script


def tools_of(agent: InsuranceAgent) -> dict[str, list[str]]:
    """Each subagent's tool names."""
    return {spec["name"]: sorted(tool.name for tool in spec.get("tools", [])) for spec in agent.subagents()}


def test_agent_roles_hold_their_tools_only() -> None:
    server = ToolOntology(["onto_load", "onto_query", "onto_stats"])
    roles = tools_of(InsuranceAgent(script(), server))
    assert roles == {
        "ontologo": ["onto_query", "onto_stats"],
        "consultas": ["consultar_poliza"],
        "transacciones": ["consultar_poliza"],
    }


def test_agent_transacciones_proposes_through_middleware() -> None:
    spec = next(
        each for each in InsuranceAgent(script(), FakeOntology()).subagents() if each["name"] == "transacciones"
    )
    assert sorted(tool.name for tool in spec["middleware"][0].tools) == ["proponer_denuncia", "proponer_endoso"]


async def test_agent_policy_queries_by_local_name() -> None:
    server = FakeOntology()
    await InsuranceAgent(script(), server).policy("pol-1001")
    tool, args = server.calls[0]
    assert tool == "onto_query"
    assert "seg:pol-1001 a seg:Poliza" in args["query"]


async def test_agent_policy_refuses_unsafe_name() -> None:
    server = FakeOntology()
    with pytest.raises(ToolException, match="pol-1001"):
        await InsuranceAgent(script(), server).policy("pol-1001 } DROP")
    assert server.calls == []
