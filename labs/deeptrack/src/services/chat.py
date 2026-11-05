"""services/chat: ChatService — one chat turn over the outer graph, tracked by etrack.

A turn is a run: a fresh run id — the trace id in every backend etrack's sinks feed — and a config carrying etrack's
source; the frames go to the bus, never to the caller. The thread id is the conversation (the checkpointer's key, the
traces' session); the agents' versions ride the run's metadata under `app.`, lifted onto its root span. After the graph
returns, the checkpoint says whether it stopped for approval: deterministic, no parsing."""

import uuid
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from typing import Any

from beartype import beartype
from etrack.logic.api import Tracker
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from infra.errors import GuardError
from models.proposal import Decision
from models.turn import ChatRun, ChatTurn

RECURSION: int = 120


@beartype
class ChatService:
    """The outer graph, etrack's tracker, where a run's trace opens, and the versions of the agents it runs."""

    __slots__ = ("_graph", "_traces", "_tracker", "_versions")

    def __init__(
        self,
        graph: CompiledStateGraph,
        tracker: Tracker[RunnableConfig],
        traces: str = "",
        versions: Mapping[str, str] | None = None,
    ) -> None:
        self._graph = graph
        self._tracker = tracker
        self._traces = traces
        self._versions = dict(versions or {})

    @staticmethod
    def _turn_input(message: str | Decision) -> dict[str, Any] | Command:
        match message:
            case Decision():
                return Command(resume=str(message))
            case _:
                return {"messages": [HumanMessage(message)]}

    @staticmethod
    def _turn_reply(values: dict[str, Any]) -> str:
        said = [each for each in values.get("messages", []) if isinstance(each, AIMessage) and each.text]
        return said[-1].text if said else ""

    ############################################################

    @property
    def graph(self) -> CompiledStateGraph:
        """The compiled outer graph — what a protocol adapter (AG-UI) drives with a run's config."""
        return self._graph

    @contextmanager
    def run(self, thread: str) -> Generator[ChatRun]:
        """A fresh run on `thread`, tracked for the block: its ids, its trace's address and the config to run it with."""
        run_id = uuid.uuid7().hex
        base: RunnableConfig = {
            "configurable": {"thread_id": thread},
            "metadata": {"app.agents": self._versions},
            "run_name": "deeptrack",
            "recursion_limit": RECURSION,
        }
        url = f"{self._traces}/{run_id}" if self._traces else ""
        with self._tracker.track(thread, base, run_id=run_id) as tracked:
            yield ChatRun(run_id=run_id, trace_id=run_id, url=url, config=tracked.config)

    async def turn(self, thread: str, message: str | Decision) -> ChatTurn:
        """One run: a user message, or the operator's decision resuming an approval stop."""
        with self.run(thread) as run:
            try:
                await self._graph.ainvoke(self._turn_input(message), run.config)
            except GuardError as stop:
                return ChatTurn(
                    run_id=run.run_id, trace_id=run.trace_id, url=run.url, reply=stop.message, blocked=stop.label
                )
            snapshot = await self._graph.aget_state(run.config)
        return ChatTurn(
            run_id=run.run_id,
            trace_id=run.trace_id,
            url=run.url,
            reply=self._turn_reply(snapshot.values),
            interrupt=next((each.value for each in snapshot.interrupts), None),
        )
