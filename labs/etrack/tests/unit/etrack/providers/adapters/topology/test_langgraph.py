"""tests/unit/etrack/providers/adapters/topology/langgraph: a compiled graph read as nodes and arcs, deep agents included."""

from typing import Any

import pytest
from deepagents import create_deep_agent
from langgraph.graph import END, START, MessagesState

from etrack.infra.errors import SourceError
from etrack.ports.topology import TopologyPort
from etrack.providers.adapters.topology.langgraph import LanggraphTopologyAdapter
from support.graph import state_graph
from support.model import script


def looped() -> Any:
    def step(state: MessagesState) -> dict[str, Any]:
        return {}

    graph = state_graph(MessagesState)
    graph.add_node("agent", step)
    graph.add_node("gate", step)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", "gate")
    graph.add_conditional_edges("gate", lambda state: END, {"agent": "agent", "end": END})
    return graph.compile()


async def test_langgraph_meets_port() -> None:
    async with LanggraphTopologyAdapter() as adapter:
        assert isinstance(adapter, TopologyPort)
        assert await adapter.health()


async def test_langgraph_reads_nodes_and_arcs() -> None:
    topology = LanggraphTopologyAdapter().read(looped())
    assert {node.id for node in topology.nodes} == {"__start__", "agent", "gate", "__end__"}
    entries = [node.id for node in topology.nodes if node.entry]
    exits = [node.id for node in topology.nodes if node.exit]
    assert (entries, exits) == (["__start__"], ["__end__"])
    arcs = {(edge.source, edge.target, edge.conditional, edge.label) for edge in topology.edges}
    assert ("gate", "__end__", True, "end") in arcs
    assert ("agent", "gate", False, "") in arcs


async def test_langgraph_deep_agent_nodes() -> None:
    topology = LanggraphTopologyAdapter().read(create_deep_agent(model=script("x")))
    assert {"__start__", "model", "tools", "__end__"} <= {node.id for node in topology.nodes}


async def test_langgraph_rejects_non_graph() -> None:
    with pytest.raises(SourceError, match="not a compiled graph"):
        LanggraphTopologyAdapter().read(object())
