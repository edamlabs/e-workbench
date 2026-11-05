"""tests/benchmark/etrack/logic/channel: what one emission costs the producer — validate, publish, forward."""

import statistics
import time
from typing import Final

import pytest

from etrack.logic.channel import EventChannel
from etrack.providers.adapters.bus.anyio import AnyioBusAdapter
from unit.etrack.conftest import RecordingSink, frame

ROUNDS: Final[int] = 2000
### a token stream at 200 tokens/s leaves 5 ms per token: the producer's share must be a sliver of it.
BUDGET_US: Final[float] = 100.0


@pytest.mark.slow
async def test_channel_emit_cost() -> None:
    sink = RecordingSink()
    async with AnyioBusAdapter() as bus:
        bus.subscribe(sink)
        channel = EventChannel(bus, forward=None)
        events = [frame(seq) for seq in range(ROUNDS)]
        spent = [(time.perf_counter_ns(), channel.emit(event), time.perf_counter_ns()) for event in events]
    costs = sorted((end - begin) / 1000 for begin, _, end in spent)
    p50, p99 = statistics.median(costs), costs[int(len(costs) * 0.99)]
    print(f"emit p50={p50:.1f}µs p99={p99:.1f}µs over {ROUNDS}")  # noqa: T201 — a benchmark reports its numbers
    assert p50 < BUDGET_US
