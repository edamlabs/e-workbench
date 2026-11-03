"""tests/unit/etrack/providers/adapters/bus/anyio: fan-out — order, isolation, drops, selects, threads, drain."""

import threading
import time
from typing import ClassVar

import anyio
import msgspec
import pytest

from etrack.infra.config.providers.adapters.bus.anyio import AnyioSettings
from etrack.infra.errors import BusError
from etrack.models.event import EventPhase, EventView, LogView, RunEvent
from etrack.ports.bus import BusPort
from etrack.providers.adapters.bus.anyio import AnyioBusAdapter
from unit.etrack.conftest import BrokenSink, RecordingSink, SlowSink, frame


class EndsOnly(RecordingSink):
    """A sink that only takes closes, narrowed to the log view."""

    view: ClassVar[type[EventView]] = LogView
    phases: ClassVar[frozenset[EventPhase]] = frozenset({EventPhase.END})


async def test_anyio_meets_port() -> None:
    assert isinstance(AnyioBusAdapter(), BusPort)


async def test_anyio_delivers_in_order(recording: RecordingSink) -> None:
    bus = AnyioBusAdapter()
    bus.subscribe(recording)
    async with bus:
        _ = [bus.publish(frame(seq)) for seq in range(50)]
    assert [view.seq for view in recording.views] == list(range(50))  # ty: ignore[unresolved-attribute]


async def test_anyio_subscribe_after_open(recording: RecordingSink) -> None:
    async with AnyioBusAdapter() as bus:
        bus.subscribe(recording)
        bus.publish(frame())
    assert len(recording.views) == 1


async def test_anyio_phases_and_view() -> None:
    ends = EndsOnly()
    async with AnyioBusAdapter() as bus:
        bus.subscribe(ends)
        bus.publish(frame(0, EventPhase.START))
        bus.publish(frame(1, EventPhase.END))
    assert [type(view) for view in ends.views] == [LogView]


async def test_anyio_broken_sink_isolated(recording: RecordingSink) -> None:
    async with AnyioBusAdapter() as bus:
        bus.subscribe(BrokenSink())
        bus.subscribe(recording)
        _ = [bus.publish(frame(seq)) for seq in range(3)]
    assert len(recording.views) == 3
    assert bus.failed == {"broken": 3}


async def test_anyio_slow_sink_never_blocks() -> None:
    slow = SlowSink()
    async with AnyioBusAdapter(AnyioSettings(capacity=5)) as bus:
        bus.subscribe(slow)
        began = time.perf_counter()
        _ = [bus.publish(frame(seq)) for seq in range(100)]
        spent = time.perf_counter() - began
    assert spent < 0.05
    assert bus.dropped["slow"] > 0
    assert len(slow.views) + bus.dropped["slow"] == 100


@pytest.mark.parametrize(
    ("verdict", "expected"),
    [(lambda event: event, 2), (lambda event: None, 0), (lambda event: event if event.seq else None, 1)],
    ids=["keep", "drop", "pick"],
)
async def test_anyio_select(recording: RecordingSink, verdict: object, expected: int) -> None:
    async with AnyioBusAdapter() as bus:
        bus.subscribe(recording, select=verdict)  # ty: ignore[invalid-argument-type]
        bus.publish(frame(0))
        bus.publish(frame(1))
    assert len(recording.views) == expected


async def test_anyio_select_transforms(recording: RecordingSink) -> None:
    def rename(event: RunEvent) -> RunEvent:
        return msgspec.structs.replace(event, name="renamed")

    async with AnyioBusAdapter() as bus:
        bus.subscribe(recording, select=rename)
        bus.publish(frame())
    assert recording.views[0].name == "renamed"  # ty: ignore[unresolved-attribute]


async def test_anyio_foreign_thread(recording: RecordingSink) -> None:
    async with AnyioBusAdapter() as bus:
        bus.subscribe(recording)
        worker = threading.Thread(target=lambda: [bus.publish(frame(seq)) for seq in range(10)])
        worker.start()
        await anyio.to_thread.run_sync(worker.join)
        await anyio.sleep(0.01)
    assert sorted(view.seq for view in recording.views) == list(range(10))  # ty: ignore[unresolved-attribute]


async def test_anyio_repeated_names(recording: RecordingSink) -> None:
    async with AnyioBusAdapter() as bus:
        bus.subscribe(BrokenSink())
        bus.subscribe(BrokenSink())
        bus.publish(frame())
    assert bus.failed == {"broken": 1, "broken#1": 1}


async def test_anyio_publish_closed() -> None:
    with pytest.raises(BusError, match="not open"):
        AnyioBusAdapter().publish(frame())


async def test_anyio_health() -> None:
    bus = AnyioBusAdapter()
    assert not await bus.health()
    async with bus:
        assert await bus.health()
    assert not await bus.health()


async def test_anyio_exit_twice() -> None:
    bus = AnyioBusAdapter()
    await bus.__aexit__(None, None, None)
    assert bus.dropped == {}
