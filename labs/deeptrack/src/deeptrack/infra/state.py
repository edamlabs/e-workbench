"""infra.state: RuntimeState — the process's tree, sealed at startup: the adapters, then the chat built over them."""

from dataclasses import dataclass

from deeptrack.adapters.onto import OntoAdapter
from deeptrack.adapters.trace import TraceAdapter
from deeptrack.instrument.chat import TracedChat


@dataclass(frozen=True, slots=True)
class RuntimeState:
    """`onto` the two ontology sessions, `trace` the Langfuse client, `chat` the traced outer graph."""

    onto: OntoAdapter
    trace: TraceAdapter
    chat: TracedChat
