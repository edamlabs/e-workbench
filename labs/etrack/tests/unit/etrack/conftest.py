"""tests/unit/etrack: the doubles every layer's tests share — a bus that keeps what it is handed, sinks that record.

`Collector` is a `BusPort` that keeps every published event in order; `RecordingSink` a `SinkPort` that keeps every
view it is sent (whole record, every phase), `SlowSink` one that takes its time and `BrokenSink` one that always
raises. `frame` builds a valid `RunEvent` with only the fields a test cares about."""

from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar, Self

import anyio
import msgspec
import pytest

from etrack.models.event import EventKind, EventPhase, EventView, RunEvent
from etrack.ports.provider import Isolation, Locality, ProviderSpec, Workload

if TYPE_CHECKING:
    from collections.abc import Mapping

    from etrack.ports.bus import Select
    from etrack.ports.sink import SinkPort

RUN = "0" * 31 + "1"


class Collector:
    """A bus that delivers nothing: it keeps every published event, in order."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("collector", Locality.EMBEDDED, Workload.IO_BOUND, Isolation.LOOP)

    def __init__(self) -> None:
        self.events: list[RunEvent] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def health(self) -> bool:
        return True

    def publish(self, event: RunEvent) -> None:
        self.events.append(event)

    def subscribe(self, sink: SinkPort, select: Select | None = None) -> None:
        return None

    @property
    def dropped(self) -> Mapping[str, int]:
        return MappingProxyType({})


class RecordingSink:
    """A sink that keeps every view it is sent."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("recording", Locality.EMBEDDED, Workload.IO_BOUND, Isolation.LOOP)
    view: ClassVar[type[EventView]] = RunEvent
    phases: ClassVar[frozenset[EventPhase]] = frozenset(EventPhase)

    def __init__(self) -> None:
        self.views: list[EventView] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def health(self) -> bool:
        return True

    async def send(self, view: EventView) -> None:
        self.views.append(view)


class SlowSink(RecordingSink):
    """A sink that takes a while per view."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("slow", Locality.EMBEDDED, Workload.IO_BOUND, Isolation.LOOP)

    async def send(self, view: EventView) -> None:
        await anyio.sleep(0.01)
        await super().send(view)


class BrokenSink(RecordingSink):
    """A sink that refuses every view."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("broken", Locality.EMBEDDED, Workload.IO_BOUND, Isolation.LOOP)

    async def send(self, view: EventView) -> None:
        msg = "refused"
        raise RuntimeError(msg)


def frame(seq: int = 0, phase: EventPhase = EventPhase.START, **fields: Any) -> RunEvent:
    """A valid frame of run RUN: span `s{seq}` unless named, a NODE unless told otherwise."""
    base: dict[str, Any] = {"run_id": RUN, "thread_id": "t1", "seq": seq, "id": f"s{seq}", "kind": EventKind.NODE}
    return msgspec.convert({**base, "phase": phase, **fields}, RunEvent)


@pytest.fixture
def collector() -> Collector:
    return Collector()


@pytest.fixture
def recording() -> RecordingSink:
    return RecordingSink()
