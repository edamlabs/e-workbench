"""processors/layout: LayoutProcessor — a topology placed on a grid: ranks by flow, lanes by neighbours, loops marked.

O(V + E) for the loops and ranks, O(V log V) for the lanes. A DFS from the entries finds the back edges — the arcs
that close a cycle against the flow — and marks them `loop`; without them the graph is a DAG, and its topological
generations are the ranks. Within a rank, nodes are ordered by the mean lane of the nodes that feed them (barycenter),
then by id, so a layout is deterministic and arcs cross as little as one pass allows."""

from statistics import fmean
from typing import TYPE_CHECKING, Final

import rustworkx as rx

from etrack.infra.errors import LayoutError
from etrack.ports.topology import Topology, TopologyEdge, TopologyNode

if TYPE_CHECKING:
    from collections.abc import Sequence

UNPLACED: Final[float] = 0.0


class BackEdges(rx.visit.DFSVisitor):
    """Collects the arcs a depth-first walk meets pointing back at a node still open: the cycles' closing arcs."""

    def __init__(self) -> None:
        self.found: set[tuple[int, int]] = set()

    def back_edge(self, e: tuple[int, int, object]) -> None:
        self.found.add((e[0], e[1]))


class LayoutProcessor:
    """Places a topology; holds nothing between calls."""

    __slots__ = ()

    ##### PRIVATE #####

    @staticmethod
    def _place_refuse(unknown: list[str]) -> None:
        msg = f"layout: arcs reach nodes the topology does not declare: {unknown}"
        raise LayoutError(msg)

    @staticmethod
    def _place_lanes(dag: rx.PyDiGraph, generations: Sequence[Sequence[int]]) -> dict[int, tuple[int, int]]:
        grid: dict[int, tuple[int, int]] = {}
        ### each rank reads the lanes of the ranks above it: the order is the algorithm, not a style.
        for rank, generation in enumerate(generations):
            weight = {
                vertex: fmean([grid[pred][1] for pred in dag.predecessor_indices(vertex) if pred in grid] or [UNPLACED])
                for vertex in generation
            }
            ordered = sorted(generation, key=lambda vertex: (weight[vertex], dag[vertex]))
            grid |= {vertex: (rank, lane) for lane, vertex in enumerate(ordered)}
        return grid

    ############################################################

    ##### PUBLIC #####

    def place(self, topology: Topology) -> Topology:
        """The same nodes and arcs with `rank`, `lane` and `loop` set, and the grid's extent."""
        ids = [node.id for node in topology.nodes]
        unknown = sorted({end for edge in topology.edges for end in (edge.source, edge.target)} - set(ids))
        _ = unknown and self._place_refuse(unknown)
        digraph = rx.PyDiGraph(multigraph=True)
        index = dict(zip(ids, digraph.add_nodes_from(ids), strict=True))
        digraph.add_edges_from_no_data([(index[edge.source], index[edge.target]) for edge in topology.edges])
        visitor = BackEdges()
        entries = sorted(index.values(), key=lambda vertex: not topology.nodes[vertex].entry)
        rx.digraph_dfs_search(digraph, entries, visitor)
        dag = digraph.copy()
        dag.remove_edges_from(list(visitor.found))
        grid = self._place_lanes(dag, rx.topological_generations(dag))
        nodes = tuple(
            TopologyNode(
                id=node.id,
                name=node.name,
                entry=node.entry,
                exit=node.exit,
                rank=grid[index[node.id]][0],
                lane=grid[index[node.id]][1],
            )
            for node in topology.nodes
        )
        edges = tuple(
            TopologyEdge(
                id=edge.id,
                source=edge.source,
                target=edge.target,
                conditional=edge.conditional,
                label=edge.label,
                loop=(index[edge.source], index[edge.target]) in visitor.found,
            )
            for edge in topology.edges
        )
        return Topology(
            nodes=nodes,
            edges=edges,
            ranks=1 + max((rank for rank, _ in grid.values()), default=-1),
            lanes=1 + max((lane for _, lane in grid.values()), default=-1),
        )
