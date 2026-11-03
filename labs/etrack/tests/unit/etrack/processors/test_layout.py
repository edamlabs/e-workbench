"""tests/unit/etrack/processors/layout: ranks by flow, lanes by barycenter, loops marked, unknown arcs refused."""

import pytest

from etrack.infra.errors import LayoutError
from etrack.ports.topology import Topology, TopologyEdge, TopologyNode
from etrack.processors.layout import LayoutProcessor


def topology(arcs: list[tuple[str, str]], names: list[str] | None = None) -> Topology:
    ids = names or sorted({end for arc in arcs for end in arc})
    nodes = tuple(TopologyNode(id=name, name=name, entry=name == "start") for name in ids)
    edges = tuple(TopologyEdge(id=f"{a}>{b}", source=a, target=b) for a, b in arcs)
    return Topology(nodes=nodes, edges=edges)


async def test_layout_ranks_chain() -> None:
    placed = LayoutProcessor().place(topology([("start", "a"), ("a", "b"), ("b", "end")]))
    assert {node.id: node.rank for node in placed.nodes} == {"start": 0, "a": 1, "b": 2, "end": 3}
    assert (placed.ranks, placed.lanes) == (4, 1)


async def test_layout_loop_marked() -> None:
    placed = LayoutProcessor().place(
        topology([("start", "agent"), ("agent", "gate"), ("gate", "agent"), ("gate", "end")])
    )
    loops = [(edge.source, edge.target) for edge in placed.edges if edge.loop]
    assert loops == [("gate", "agent")]
    assert {node.id: node.rank for node in placed.nodes}["gate"] == 2


async def test_layout_lanes_fan_out() -> None:
    placed = LayoutProcessor().place(topology([("start", "x"), ("start", "y"), ("x", "end"), ("y", "end")]))
    lanes = {node.id: (node.rank, node.lane) for node in placed.nodes}
    assert lanes["x"] == (1, 0)
    assert lanes["y"] == (1, 1)
    assert placed.lanes == 2


async def test_layout_empty() -> None:
    placed = LayoutProcessor().place(Topology(nodes=(), edges=()))
    assert (placed.ranks, placed.lanes) == (0, 0)


async def test_layout_refuses_unknown_arc() -> None:
    with pytest.raises(LayoutError, match="ghost"):
        LayoutProcessor().place(topology([("start", "ghost")], names=["start"]))
