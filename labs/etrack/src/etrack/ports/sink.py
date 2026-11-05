"""ports/sink: a client of the event stream — it declares the view it reads and the phases it wants, and takes views.

A sink never sees the whole record: the bus narrows each event onto the sink's `view` before handing it over, and
skips the phases the sink did not ask for before queueing — a sink that ignores token deltas never pays for them."""

from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

from etrack.ports.provider import Provider

if TYPE_CHECKING:
    from etrack.models.event import EventPhase, EventView


@runtime_checkable
class SinkPort(Provider, Protocol):
    """A consumer of views: what it reads, which phases reach it, and the one call that delivers."""

    view: ClassVar[type[EventView]]
    phases: ClassVar[frozenset[EventPhase]]

    async def send(self, view: EventView) -> None: ...
