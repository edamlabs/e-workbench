"""tests/support/track: a sink that keeps every frame and knows when a run is over, and a tracker for unit graphs.

Frames reach sinks through the bus, after the turn returns: `settled(run_id)` waits for the run's root to close (END or
ERROR) and hands back that run's frames, in order. `tracked()` opens a real in-process bus with a recorder on it and
builds the tracker the lifespan would — no providers, no network."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, ClassVar, Final, Self, cast

import anyio
from etrack.logic.api import Tracker
from etrack.logic.channel import EventChannel
from etrack.models.event import EventKind, EventPhase, EventView, RunEvent
from etrack.ports.bus import BusPort
from etrack.ports.provider import Isolation, Locality, ProviderSpec, Workload
from etrack.providers.adapters.bus.anyio import AnyioAdapter
from etrack.providers.adapters.source.langgraph import LanggraphSourceAdapter
from etrack.providers.drivers.sink.otlp import OtlpDriver
from langchain_core.runnables import RunnableConfig

from infra.config.providers import SinkKind
from ops.mask import mask_data

CLOSES: Final[frozenset[EventPhase]] = frozenset({EventPhase.END, EventPhase.ERROR})
WAIT: Final[float] = 10.0


class Recorder:
    """Every frame the bus delivers, and an event per run that fires when the run's root closes."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("recorder", Locality.EMBEDDED, Workload.IO_BOUND, Isolation.LOOP)
    view: ClassVar[type[EventView]] = RunEvent
    phases: ClassVar[frozenset[EventPhase]] = frozenset(EventPhase)

    def __init__(self) -> None:
        self.events: list[RunEvent] = []
        self._closed: dict[str, anyio.Event] = {}

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def health(self) -> bool:
        return True

    async def send(self, view: EventView) -> None:
        event = RunEvent.project(view)
        self.events.append(event)
        _ = (
            event.kind is EventKind.RUN
            and event.phase in CLOSES
            and self._closed.setdefault(event.run_id, anyio.Event()).set()
        )

    async def settled(self, run_id: str) -> list[RunEvent]:
        """The run's frames, once its root has closed."""
        with anyio.fail_after(WAIT):
            await self._closed.setdefault(run_id, anyio.Event()).wait()
        return [event for event in self.events if event.run_id == run_id]


def record(bus: BusPort) -> Recorder:
    """A recorder subscribed to a bus already serving."""
    recorder = Recorder()
    bus.subscribe(recorder)
    return recorder


@asynccontextmanager
async def tracked(mcp: frozenset[str] = frozenset()) -> AsyncGenerator[tuple[Tracker[RunnableConfig], Recorder]]:
    """A tracker over a real bus, and the recorder on it — the lifespan's wiring, in memory."""
    async with AnyioAdapter() as bus:
        recorder = record(bus)
        channel = EventChannel(bus, forward=None)
        yield (
            Tracker(channel, LanggraphSourceAdapter(mcp=mcp), redact=lambda payload: mask_data(data=payload)),
            recorder,
        )


async def exported(state: Any) -> None:
    """Every span of the runs so far exported by the OTLP sink: a beat for its bus worker, then a flush."""
    otlp = cast("OtlpDriver", state.providers.track.sinks[SinkKind.OTLP])
    await anyio.sleep(0.2)
    await otlp.flush()
