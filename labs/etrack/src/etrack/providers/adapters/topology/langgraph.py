"""providers/adapters/topology/langgraph: LanggraphTopologyAdapter — a compiled LangGraph read as its declared map.

`get_graph(xray=True)` opens compiled subgraphs into their own nodes (`agent:model`), so a deep agent mounted as a
node shows its inner steps. `__start__` and `__end__` stay as nodes: a canvas draws where a run enters and leaves. A
subagent a deep agent launches through a tool is not declared anywhere — it appears only in the live span tree."""

from typing import Any, ClassVar, Final, Self

from langgraph.constants import END, START

from etrack.infra.errors import SourceError
from etrack.infra.logger import logger
from etrack.ports.provider import Isolation, Locality, ProviderSpec, Workload
from etrack.ports.topology import Topology, TopologyEdge, TopologyNode

XRAY: Final[bool] = True


class LanggraphTopologyAdapter:
    """Reads any compiled LangGraph graph; holds nothing between reads."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("langgraph", Locality.EMBEDDED, Workload.CPU_BOUND, Isolation.LOOP)

    __slots__ = ()

    ##### PRIVATE #####

    @staticmethod
    def _read_drawable(graph: object) -> Any:
        match getattr(graph, "get_graph", None):
            case None:
                msg = f"langgraph: {type(graph).__name__} is not a compiled graph (no get_graph)"
                raise SourceError(msg)
            case drawable:
                return drawable(xray=XRAY)

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        logger.info("topology opened", source="langgraph")
        return self

    async def __aexit__(self, *exc: object) -> None:
        logger.info("topology closed", source="langgraph")

    async def health(self) -> bool:
        """Always ready: the adapter holds no resource."""
        return True

    def read(self, graph: object) -> Topology:
        """The declared nodes and arcs, unplaced; an arc's label is the router's branch name when it has one."""
        drawn = self._read_drawable(graph)
        nodes = tuple(
            TopologyNode(id=key, name=str(node.name), entry=key == START, exit=key == END)
            for key, node in drawn.nodes.items()
        )
        edges = tuple(
            TopologyEdge(
                id=f"{edge.source}>{edge.target}:{index}",
                source=edge.source,
                target=edge.target,
                conditional=bool(edge.conditional),
                label=str(edge.data or ""),
            )
            for index, edge in enumerate(drawn.edges)
        )
        return Topology(nodes=nodes, edges=edges)
