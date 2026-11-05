"""tests/unit/etrack/logic/api: Tracker — a run tracked end to end, from a host's config to frames on the channel."""

import threading
import uuid
from typing import Any

import structlog
from deepagents import create_deep_agent
from langchain_core.tools import tool
from langgraph.graph import START, MessagesState

from etrack.logic.api import Tracker
from etrack.logic.channel import EventChannel
from etrack.models.event import EventKind, EventPhase, RunEvent
from etrack.providers.adapters.bus.anyio import AnyioBusAdapter
from etrack.providers.adapters.source.langgraph import LanggraphSourceAdapter
from support.graph import state_graph
from support.model import call, script
from unit.etrack.conftest import RUN, Collector, RecordingSink


def graph() -> Any:
    model = script("hola")

    async def agent(state: MessagesState) -> dict[str, Any]:
        return {"messages": [await model.ainvoke(state["messages"])]}

    built = state_graph(MessagesState)
    built.add_node("agent", agent)
    built.add_edge(START, "agent")
    return built.compile()


async def test_tracker_run_frames(collector: Collector) -> None:
    tracker = Tracker(EventChannel(collector), LanggraphSourceAdapter())
    with tracker.track("t1", {}) as tracked:
        await graph().ainvoke({"messages": [("user", "hi")]}, tracked.config)
    assert collector.events[0].id == tracked.scope.run_id
    assert {event.thread_id for event in collector.events} == {"t1"}
    assert [event.seq for event in collector.events] == list(range(len(collector.events)))


async def test_tracker_given_run_id(collector: Collector) -> None:
    with Tracker(EventChannel(collector), LanggraphSourceAdapter()).track("t1", {}, run_id=RUN) as tracked:
        assert tracked.scope.run_id == RUN
        assert tracked.config.get("run_id") == uuid.UUID(RUN)


async def test_tracker_binds_contextvars(collector: Collector) -> None:
    with Tracker(EventChannel(collector), LanggraphSourceAdapter()).track("t1", {}) as tracked:
        bound = structlog.contextvars.get_contextvars()
    assert (bound["run_id"], bound["thread_id"]) == (tracked.scope.run_id, "t1")
    assert "run_id" not in structlog.contextvars.get_contextvars()


async def test_tracker_redacts(collector: Collector) -> None:
    tracker = Tracker(EventChannel(collector), LanggraphSourceAdapter(), redact=lambda payload: {})
    with tracker.track("t1", {}) as tracked:
        await graph().ainvoke({"messages": [("user", "secret")]}, tracked.config)
    assert all(event.payload == {} for event in collector.events)


async def test_tracker_own_span(collector: Collector) -> None:
    with Tracker(EventChannel(collector), LanggraphSourceAdapter()).track("t1", {}) as tracked:
        await graph().ainvoke({"messages": [("user", "hi")]}, tracked.config)
        with tracked.fold.span("gate", kind=EventKind.EVALUATION):
            pass
    gate = [event for event in collector.events if event.kind is EventKind.EVALUATION]
    assert [event.phase for event in gate] == [EventPhase.START, EventPhase.END]
    assert gate[0].parent == tracked.scope.run_id


async def test_tracker_sync_tool_through_bus() -> None:
    @tool
    def lento(x: int) -> str:
        """A blocking tool: LangGraph runs it on a worker thread."""
        return f"hecho {x} en {threading.current_thread().name}"

    sink = RecordingSink()
    async with AnyioBusAdapter() as bus:
        bus.subscribe(sink)
        tracker = Tracker(EventChannel(bus, forward=None), LanggraphSourceAdapter())
        agent = create_deep_agent(model=script(call("lento", "c1", x=1), "ok"), tools=[lento])
        with tracker.track("t1", {}) as tracked:
            await agent.ainvoke({"messages": [("user", "hi")]}, tracked.config)
    frames = [view for view in sink.views if isinstance(view, RunEvent)]
    tools = [view for view in frames if view.kind is EventKind.TOOL]
    assert [view.phase for view in tools] == [EventPhase.START, EventPhase.END]
    assert sorted(view.seq for view in frames) == list(range(len(frames)))
    assert frames[0].id == tracked.scope.run_id
