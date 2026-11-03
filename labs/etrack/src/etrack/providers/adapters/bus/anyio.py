"""providers/adapters/bus/anyio: AnyioBusAdapter — one bounded stream and one worker per sink, publish never waits.

`publish` is synchronous and returns at once: on the loop's thread it queues the event on every sink that takes its
phase; from any other thread it hops onto the loop first. A full stream drops the event for that sink alone and counts
it. Each worker applies the subscription's `Select`, narrows the event onto the sink's view and awaits `send`; a
select or a sink that raises is logged and skipped, never the producer's problem nor another sink's. Leaving the bus
closes every stream, lets each worker deliver what is still queued, then stops."""

import asyncio
import threading
from collections import Counter
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar, Self

import anyio

from etrack.infra.errors import BusError
from etrack.infra.logger import logger
from etrack.infra.settings import settings as st
from etrack.models.event import RunEvent
from etrack.ports.provider import Isolation, Locality, ProviderSpec, Workload

if TYPE_CHECKING:
    from collections.abc import Mapping

    from anyio.abc import TaskGroup
    from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

    from etrack.infra.config.providers.adapters.bus.anyio import AnyioSettings
    from etrack.ports.bus import Select
    from etrack.ports.sink import SinkPort


@dataclass(slots=True)
class Subscription:
    """One sink, its policy, and the bounded stream between the bus and its worker."""

    name: str
    sink: SinkPort
    select: Select | None
    send: MemoryObjectSendStream[RunEvent]
    receive: MemoryObjectReceiveStream[RunEvent]


class AnyioBusAdapter:
    """The in-process fan-out: sinks subscribe before or after it opens; events reach each sink in publish order."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("anyio", Locality.EMBEDDED, Workload.IO_BOUND, Isolation.LOOP)

    __slots__ = ("_dropped", "_failed", "_group", "_loop", "_settings", "_subs", "_thread")

    def __init__(self, settings: AnyioSettings | None = None) -> None:
        self._settings = settings
        self._subs: list[Subscription] = []
        self._dropped: Counter[str] = Counter()
        self._failed: Counter[str] = Counter()
        self._group: TaskGroup | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: int | None = None

    ##### PRIVATE #####

    @property
    def _common_capacity(self) -> int:
        return (self._settings or st.providers.adapters.bus.anyio).capacity

    def _subscribe_start(self, sub: Subscription) -> None:
        ### a sink subscribed before the bus opens starts with it; one subscribed after starts at once.
        match self._group:
            case None:
                pass
            case group:
                group.start_soon(self._subscribe_serve, sub)

    async def _subscribe_serve(self, sub: Subscription) -> None:
        ### a worker is a loop by nature, alive as long as its stream: a comprehension would keep one item per event.
        async with sub.receive:
            async for event in sub.receive:
                await self._subscribe_deliver(sub, event)

    async def _subscribe_deliver(self, sub: Subscription, event: RunEvent) -> None:
        try:
            chosen = sub.select(event) if sub.select else event
            _ = chosen is not None and await sub.sink.send(sub.sink.view.project(chosen))
        except Exception as failure:  # noqa: BLE001 — a sink's failure is its own, never the producer's nor a sibling's
            self._failed[sub.name] += 1
            logger.warning("bus delivery failed", sink=sub.name, error=f"{type(failure).__name__}: {failure}")

    def _publish_local(self, event: RunEvent) -> None:
        _ = [self._publish_one(sub, event) for sub in self._subs if event.phase in sub.sink.phases]

    def _publish_one(self, sub: Subscription, event: RunEvent) -> None:
        try:
            sub.send.send_nowait(event)
        except anyio.WouldBlock, anyio.ClosedResourceError, anyio.BrokenResourceError:
            self._dropped[sub.name] += 1

    def _publish_loop(self) -> asyncio.AbstractEventLoop:
        match self._loop:
            case None:
                msg = "AnyioBusAdapter is not open: the lifespan opens it before any run"
                raise BusError(msg)
            case loop:
                return loop

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        self._loop = asyncio.get_running_loop()
        self._thread = threading.get_ident()
        self._group = anyio.create_task_group()
        await self._group.__aenter__()
        _ = [self._subscribe_start(sub) for sub in self._subs]
        logger.info("bus opened", sinks=[sub.name for sub in self._subs], capacity=self._common_capacity)
        return self

    async def __aexit__(self, *exc: object) -> None:
        match self._group:
            case None:
                return
            case group:
                ### closing the send side lets each worker drain what is queued, then end on its own.
                _ = [sub.send.close() for sub in self._subs]
                await group.__aexit__(None, None, None)
                self._group, self._loop, self._thread = None, None, None
                logger.info("bus closed", dropped=dict(self._dropped), failed=dict(self._failed))

    async def health(self) -> bool:
        """Open: the workers run and publish is accepted."""
        return self._group is not None

    def subscribe(self, sink: SinkPort, select: Select | None = None) -> None:
        """A sink served from now on, through `select` when given; named by its spec, numbered when repeated."""
        taken = sum(sub.sink.spec.name == sink.spec.name for sub in self._subs)
        name = sink.spec.name if taken == 0 else f"{sink.spec.name}#{taken}"
        send, receive = anyio.create_memory_object_stream[RunEvent](self._common_capacity)
        sub = Subscription(name=name, sink=sink, select=select, send=send, receive=receive)
        self._subs.append(sub)
        self._subscribe_start(sub)

    def publish(self, event: RunEvent) -> None:
        """Queue the event for every sink that takes its phase; from a foreign thread, hop onto the loop first."""
        loop = self._publish_loop()
        match threading.get_ident() == self._thread:
            case True:
                self._publish_local(event)
            case _:
                loop.call_soon_threadsafe(self._publish_local, event)

    @property
    def dropped(self) -> Mapping[str, int]:
        """Events lost per sink because its stream was full or closed."""
        return MappingProxyType(dict(self._dropped))

    @property
    def failed(self) -> Mapping[str, int]:
        """Deliveries that raised, per sink."""
        return MappingProxyType(dict(self._failed))
