"""ports/topology: the graph a system declares, before it runs — nodes, arcs, and where each sits on a grid.

A topology adapter reads a framework's compiled graph into these values; the layout processor places them. `rank` is
the step from the entry, `lane` the slot within it; `loop` marks the arc that closes a cycle against the flow."""

from typing import Protocol, runtime_checkable

import msgspec

from etrack.ports.provider import Provider


##### VALUES #####
class TopologyNode(msgspec.Struct, frozen=True, kw_only=True):
    """One declared node: its id, the name a span carries when it runs, and its place once laid out."""

    id: str
    name: str
    entry: bool = False
    exit: bool = False
    rank: int = 0
    lane: int = 0


class TopologyEdge(msgspec.Struct, frozen=True, kw_only=True):
    """One declared arc: conditional when a router chooses it, `loop` when it closes a cycle."""

    id: str
    source: str
    target: str
    conditional: bool = False
    label: str = ""
    loop: bool = False


class Topology(msgspec.Struct, frozen=True, kw_only=True):
    """The declared graph: its nodes, its arcs, and the grid's extent once placed."""

    nodes: tuple[TopologyNode, ...]
    edges: tuple[TopologyEdge, ...]
    ranks: int = 0
    lanes: int = 0


##### PORT #####
@runtime_checkable
class TopologyPort(Provider, Protocol):
    """A framework's compiled graph read as a topology, unplaced."""

    def read(self, graph: object) -> Topology: ...
