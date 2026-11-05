"""tests/unit/tools/policy: `consultar_poliza` reads one policy by its local name, and refuses anything else unsent."""

import pytest
from langchain_core.tools import ToolException

from tests.support.fake import FakeOntology
from tools.policy import NAME, PolicyTool


async def test_policy_queries_by_local_name() -> None:
    server = FakeOntology()
    await PolicyTool(server).run("pol-1001")
    tool, args = server.calls[0]
    assert tool == "onto_query"
    assert "seg:pol-1001 a seg:Poliza" in args["query"]


async def test_policy_refuses_unsafe_name() -> None:
    server = FakeOntology()
    with pytest.raises(ToolException, match="pol-1001"):
        await PolicyTool(server).run("pol-1001 } DROP")
    assert server.calls == []


async def test_policy_tool_named_for_agents() -> None:
    assert PolicyTool(FakeOntology()).tool.name == NAME == "consultar_poliza"
