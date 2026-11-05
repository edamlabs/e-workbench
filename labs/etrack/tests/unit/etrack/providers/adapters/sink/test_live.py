"""tests/unit/etrack/providers/adapters/sink/live: per-thread replay by offset, live push, lag cut-off, eviction."""

import anyio
import pytest

from etrack.infra.config.providers.adapters.sink.live import LiveSettings
from etrack.ports.sink import SinkPort
from etrack.providers.adapters.sink.live import LiveFrame, LiveSinkAdapter
from unit.etrack.conftest import frame


async def take(live: LiveSinkAdapter, thread: str, after: int, count: int) -> list[LiveFrame]:
    seen: list[LiveFrame] = []
    with anyio.fail_after(1):
        async for each in live.watch(thread, after):
            seen.append(each)
            if len(seen) == count:
                break
    return seen


async def test_live_meets_port() -> None:
    async with LiveSinkAdapter() as live:
        assert isinstance(live, SinkPort)
        assert await live.health()


async def test_live_offsets_per_thread() -> None:
    live = LiveSinkAdapter()
    _ = [await live.send(frame(seq, thread_id=thread)) for seq, thread in enumerate(["a", "b", "a"])]
    assert (live.offset("a"), live.offset("b"), live.offset("never")) == (2, 1, 0)


@pytest.mark.parametrize(("after", "expected"), [(-1, [0, 1, 2]), (0, [1, 2]), (2, [])], ids=["all", "past", "none"])
async def test_live_replay(after: int, expected: list[int]) -> None:
    live = LiveSinkAdapter()
    _ = [await live.send(frame(seq)) for seq in range(3)]
    seen = await take(live, "t1", after, len(expected)) if expected else []
    assert [each.offset for each in seen] == expected


async def test_live_replay_then_follow() -> None:
    live = LiveSinkAdapter()
    await live.send(frame(0))
    seen: list[LiveFrame] = []

    async def watch() -> None:
        seen.extend(await take(live, "t1", -1, 3))

    async with anyio.create_task_group() as group:
        group.start_soon(watch)
        await anyio.sleep(0.01)
        await live.send(frame(1))
        await live.send(frame(2))
    assert [each.event.seq for each in seen] == [0, 1, 2]


async def test_live_buffer_bounded() -> None:
    live = LiveSinkAdapter(LiveSettings(buffer=2))
    _ = [await live.send(frame(seq)) for seq in range(5)]
    assert [each.offset for each in await take(live, "t1", -1, 2)] == [3, 4]


async def test_live_lagging_watcher_cut() -> None:
    live = LiveSinkAdapter(LiveSettings(backlog=1))
    watcher = live.watch("t1")
    pending = anext(watcher)
    await live.send(frame(0))
    first = await pending
    _ = [await live.send(frame(seq)) for seq in range(1, 5)]
    rest = [each async for each in watcher]
    assert first.offset == 0
    assert len(rest) < 4


async def test_live_evicts_oldest_thread() -> None:
    live = LiveSinkAdapter(LiveSettings(threads=2))
    _ = [await live.send(frame(seq, thread_id=thread)) for seq, thread in enumerate(["a", "b", "c"])]
    assert (live.offset("a"), live.offset("b"), live.offset("c")) == (0, 1, 1)


async def test_live_exit_closes_watchers() -> None:
    live = LiveSinkAdapter()
    await live.send(frame(0))
    watcher = live.watch("t1")
    assert (await anext(watcher)).offset == 0
    await live.__aexit__(None, None, None)
    assert [each async for each in watcher] == []
