"""ports/source: where a framework's run enters — a source turns the framework's own hooks into edges of a span tree.

A source knows its framework and nothing of what follows: it reports each span it sees as an `Edge` (its `kind`, or
`None` for plumbing the tree folds away), each streamed piece as a delta, each close with what it left. The
`FoldPort` behind it orders, parents and stamps them. `bind` takes the host's own run configuration and hands it back
with the source's hook attached and the run's id pinned, so the framework names the run as the tree does."""

from typing import Any, Protocol, runtime_checkable

import msgspec

from etrack.models.event import EventKind, Failure, ModelRef, Part, RunScope, Usage
from etrack.ports.provider import Provider


##### VALUES #####
class Edge(msgspec.Struct, frozen=True, kw_only=True):
    """A span as a source first sees it: its id, its raw parent, what it is — `None` when it is plumbing — and where."""

    id: str
    parent: str = ""
    kind: EventKind | None
    name: str = ""
    node: str = ""
    ns: str = ""
    step: int | None = None
    message_id: str = ""
    call_id: str = ""
    model: ModelRef | None = None
    payload: dict[str, Any] = msgspec.field(default_factory=dict)
    attributes: dict[str, Any] = msgspec.field(default_factory=dict)


##### PORTS #####
@runtime_checkable
class FoldPort(Protocol):
    """What a source reports to: spans opened, pieces streamed, spans closed, and frames that open and close at once."""

    def open(self, edge: Edge) -> None: ...

    def delta(self, span: str, part: Part, payload: dict[str, Any], call_id: str = "") -> None: ...

    def close(
        self, span: str, payload: dict[str, Any], usage: Usage | None = None, error: Failure | None = None
    ) -> None: ...

    def instant(self, edge: Edge) -> None: ...


@runtime_checkable
class SourcePort[C](Provider, Protocol):
    """A framework's run hooked to a fold: the host's config in, the same config with the hook and the run id out."""

    def bind(self, fold: FoldPort, scope: RunScope, config: C) -> C: ...
