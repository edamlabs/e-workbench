"""tests/unit/etrack/logic/channel: the log as the bus — validate, publish, forward, never touch the host's config."""

import logging
from typing import Any

import msgspec
import pytest
import structlog
from structlog.testing import capture_logs

from etrack.infra.errors import ChannelError
from etrack.logic.channel import EVENT, LEVELS, EventChannel
from etrack.models.event import EventPhase, RunEvent
from unit.etrack.conftest import RUN, Collector, frame

KEYS: dict[str, Any] = {"run_id": RUN, "seq": 0, "id": "s0", "kind": "node", "phase": "start"}


async def test_channel_emit_publishes_as_is(collector: Collector) -> None:
    event = frame()
    EventChannel(collector).emit(event)
    assert collector.events == [event]


async def test_channel_log_keys_validated(collector: Collector) -> None:
    EventChannel(collector).log.info(EVENT, **KEYS)
    expected = msgspec.convert({**KEYS, "at": collector.events[0].at}, RunEvent)
    assert collector.events[0] == expected


async def test_channel_log_contextvars(collector: Collector) -> None:
    keys = {key: value for key, value in KEYS.items() if key != "run_id"}
    with structlog.contextvars.bound_contextvars(run_id=RUN, thread_id="t9"):
        EventChannel(collector).log.info(EVENT, **keys)
    assert (collector.events[0].run_id, collector.events[0].thread_id) == (RUN, "t9")


@pytest.mark.parametrize(
    "broken",
    [{"kind": "planet"}, {"seq": "x"}, {"id": None}],
    ids=["kind", "seq", "id"],
)
async def test_channel_log_rejects(collector: Collector, broken: dict[str, Any]) -> None:
    with pytest.raises(ChannelError, match="not a RunEvent"):
        EventChannel(collector).log.info(EVENT, **{**KEYS, **broken})
    assert collector.events == []


async def test_channel_model_subclass(collector: Collector) -> None:
    class AppEvent(RunEvent, frozen=True, kw_only=True):
        tenant: str

    channel = EventChannel(collector, model=AppEvent)
    channel.log.info(EVENT, **KEYS, tenant="acme")
    assert channel.model is AppEvent
    assert collector.events[0].tenant == "acme"  # ty: ignore[unresolved-attribute]


@pytest.mark.parametrize("phase", list(EventPhase), ids=[str(phase) for phase in EventPhase])
async def test_channel_forward_level(collector: Collector, phase: EventPhase) -> None:
    with capture_logs() as lines:
        EventChannel(collector).emit(frame(phase=phase, payload={"secret": 1}))
    (line,) = lines
    assert line["log_level"] == logging.getLevelName(LEVELS[phase]).lower()
    assert (line["event"], line["id"]) == (EVENT, "s0")
    assert "payload" not in line
    assert "parent" not in line  # empty fields stay off the line


async def test_channel_forward_off(collector: Collector) -> None:
    with capture_logs() as lines:
        EventChannel(collector, forward=None).emit(frame())
    assert lines == []
    assert len(collector.events) == 1


async def test_channel_ignores_host_level(collector: Collector) -> None:
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(50))
    try:
        EventChannel(collector).emit(frame(phase=EventPhase.DELTA))
    finally:
        structlog.reset_defaults()
    assert len(collector.events) == 1
