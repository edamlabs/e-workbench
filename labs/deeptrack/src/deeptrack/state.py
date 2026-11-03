"""deeptrack/state: the typed branches of the process tree — what each lifespan mounts, typed by port, never by brand.

The root is the dynamic `infra.state.State` the lifespans write in order; each branch below is what a constructor
returns and what a test builds by hand. `state.providers.ontology.reference` ≡ the reference server, `state.engines.shacl`
≡ `engines/shacl.py`, `state.services.chat` ≡ `deeptrack/services/chat.py`."""

from dataclasses import dataclass

from deeptrack.services.chat import ChatService
from engines.shacl import ShaclEngine
from ports.chat import ChatPort
from ports.ontology import OntologyPort
from ports.trace import TracePort


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
class ProvidersState:
    """Every provider by role, typed by the port it meets."""

    chat: ChatPort
    trace: TracePort
    ontology: OntologyState


@dataclass(frozen=True, slots=True)
class EnginesState:
    """The engines over the providers."""

    shacl: ShaclEngine


@dataclass(frozen=True, slots=True)
class ServicesState:
    """The business: one chat service over the outer graph."""

    chat: ChatService
