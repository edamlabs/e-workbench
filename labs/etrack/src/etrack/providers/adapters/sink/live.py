"""providers/adapters/sink/live: LiveSinkAdapter — every frame kept per thread for replay, and pushed to who watches.

A thread is a conversation: its frames, across runs, get a thread-wide `offset` (contiguous, from 0) and the last
`buffer` of them are kept. `watch(thread, after)` replays what is kept past the cursor, then follows live — a client
that reconnects with the last offset it saw misses nothing still buffered. A watcher that lags more than `backlog`
frames is cut off rather than slowing the bus; threads beyond `threads` are evicted, least recently written first."""

from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar, Final, Self

import anyio
import msgspec

from etrack.infra.logger import logger
from etrack.infra.settings import settings as st
from etrack.models.event import EventPhase, RunEvent
from etrack.ports.provider import Isolation, Locality, ProviderSpec, Workload

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from anyio.streams.memory import MemoryObjectSendStream

    from etrack.infra.config.providers.adapters.sink.live import LiveSettings
    from etrack.models.event import EventView

PHASES: Final[frozenset[EventPhase]] = frozenset(EventPhase)


class LiveFrame(msgspec.Struct, frozen=True, kw_only=True):
    """A frame as a watcher receives it: its place in the thread, and the event."""

    offset: int
    event: RunEvent


@dataclass(slots=True)
class LiveThread:
    """One conversation: its next offset, the frames kept, and who watches it."""

    buffer: deque[LiveFrame]
    offset: int = 0
    watchers: set[MemoryObjectSendStream[LiveFrame]] = field(default_factory=set)


class LiveSinkAdapter:
    """The live sink: the whole record, every phase, kept and pushed in memory."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("live", Locality.EMBEDDED, Workload.IO_BOUND, Isolation.LOOP)
    view: ClassVar[type[EventView]] = RunEvent
    phases: ClassVar[frozenset[EventPhase]] = PHASES

    __slots__ = ("_settings", "_threads")

    def __init__(self, settings: LiveSettings | None = None) -> None:
        self._settings = settings
        self._threads: OrderedDict[str, LiveThread] = OrderedDict()

    ##### PRIVATE #####

    @property
    def _common_settings(self) -> LiveSettings:
        return self._settings or st.providers.adapters.sink.live

    def _common_thread(self, thread: str) -> LiveThread:
        match self._threads.get(thread):
            case LiveThread() as known:
                self._threads.move_to_end(thread)
                return known
            case _:
                created = LiveThread(buffer=deque(maxlen=self._common_settings.buffer))
                self._threads[thread] = created
                _ = len(self._threads) > self._common_settings.threads and self._send_evict()
                return created

    def _send_evict(self) -> None:
        thread, evicted = self._threads.popitem(last=False)
        _ = [watcher.close() for watcher in evicted.watchers]
        logger.debug("live thread evicted", thread=thread)

    @staticmethod
    def _send_push(watched: LiveThread, frame: LiveFrame) -> None:
        cut = [watcher for watcher in watched.watchers if not LiveSinkAdapter._send_one(watcher, frame)]
        _ = [(watched.watchers.discard(watcher), watcher.close()) for watcher in cut]

    @staticmethod
    def _send_one(watcher: MemoryObjectSendStream[LiveFrame], frame: LiveFrame) -> bool:
        try:
            watcher.send_nowait(frame)
        except anyio.WouldBlock, anyio.BrokenResourceError, anyio.ClosedResourceError:
            return False
        return True

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        logger.info("live opened", buffer=self._common_settings.buffer, threads=self._common_settings.threads)
        return self

    async def __aexit__(self, *exc: object) -> None:
        _ = [watcher.close() for watched in self._threads.values() for watcher in watched.watchers]
        self._threads.clear()
        logger.info("live closed")

    async def health(self) -> bool:
        """Always ready: the buffer lives in this process."""
        return True

    async def send(self, view: EventView) -> None:
        """Keep the frame under its thread's next offset and push it to every watcher."""
        event = RunEvent.project(view)
        watched = self._common_thread(event.thread_id)
        frame = LiveFrame(offset=watched.offset, event=event)
        watched.offset += 1
        watched.buffer.append(frame)
        self._send_push(watched, frame)

    async def watch(self, thread: str, after: int = -1) -> AsyncIterator[LiveFrame]:
        """The thread's kept frames past `after`, then every new one, until the watcher lags, is evicted or leaves."""
        watched = self._common_thread(thread)
        send, receive = anyio.create_memory_object_stream[LiveFrame](self._common_settings.backlog)
        ### replay and registration happen with no await between them: no frame falls in the gap.
        replay = [frame for frame in watched.buffer if frame.offset > after]
        watched.watchers.add(send)
        ### a watch is a loop by nature, alive as long as the client: a comprehension cannot yield across awaits.
        try:
            async with receive:
                for frame in replay:
                    yield frame
                async for frame in receive:
                    yield frame
        finally:
            watched.watchers.discard(send)
            send.close()

    def offset(self, thread: str) -> int:
        """The offset the thread's next frame will take: how many frames it has had."""
        return self._threads[thread].offset if thread in self._threads else 0
