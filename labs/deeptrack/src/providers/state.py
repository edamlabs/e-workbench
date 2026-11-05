"""providers/state: the providers branch — every provider by role, typed by the port it meets, never by brand.

`state.providers.harness` holds the agents read from their directory; `state.providers.agent` builds them.

`state.providers.ontology.reference` is the reference server the agent reads; `validation` the scratch copy the SHACL
engine judges on. The lifespan builds the branch; a test builds it by hand with fakes."""

from collections.abc import Mapping
from dataclasses import dataclass

from etrack.ports.bus import BusPort
from etrack.ports.sink import SinkPort, WatchPort
from etrack.ports.source import SourcePort
from etrack.ports.topology import TopologyPort
from langchain_core.runnables import RunnableConfig

from infra.config.providers import SinkKind
from ports.agent import AgentPort
from ports.chat import ChatPort
from ports.classify import ClassifyPort
from ports.harness import HarnessPort
from ports.ontology import OntologyPort


@dataclass(frozen=True, slots=True)
class OntologyState:
    """The two ontology servers: the reference the agent reads, the scratch copy the engine validates on."""

    reference: OntologyPort
    validation: OntologyPort

    @property
    def names(self) -> frozenset[str]:
        """Every MCP tool name both servers advertise."""
        return frozenset(self.reference.tools) | frozenset(self.validation.tools)


@dataclass(frozen=True, slots=True)
class TrackState:
    """etrack's providers: the bus every frame crosses, the sinks it serves by kind, the source that reads a run."""

    bus: BusPort
    sinks: Mapping[SinkKind, SinkPort]
    source: SourcePort[RunnableConfig]
    forward: bool = True
    watch: WatchPort | None = None


@dataclass(frozen=True, slots=True)
class ProvidersState:
    """Every provider by role, typed by the port it meets."""

    chat: ChatPort
    classify: ClassifyPort
    ontology: OntologyState
    harness: HarnessPort
    agent: AgentPort
    track: TrackState
    topology: TopologyPort
