"""services/chat: ChatService — one chat turn over the outer graph, seen live by the projector and kept by the tracer.

A turn is a run: a fresh run id, its derived trace id, a projector pushing frames to the caller's sink and the
tracer's handler on the same callbacks. The thread id is the conversation (the checkpointer's key, the tracer's
session). After the graph returns, the checkpoint says whether it stopped for approval: deterministic, no parsing."""

import uuid
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from deeptrack.models.proposal import Decision
from deeptrack.models.turn import ChatRun, ChatTurn
from infra.errors import GuardError
from ports.trace import TracePort
from processors.projector import EventProjector, Sink

RECURSION: int = 120


class ChatService:
    """The outer graph, the tracer, and the MCP tool names that tell an MCP span from a plain tool."""

    __slots__ = ("_graph", "_mcp", "_trace")

    def __init__(self, graph: CompiledStateGraph, trace: TracePort, mcp: frozenset[str]) -> None:
        self._graph = graph
        self._trace = trace
        self._mcp = mcp

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

    def run(self, thread: str, sink: Sink) -> tuple[ChatRun, EventProjector]:
        """A fresh run on `thread`: its ids and config, the projector pushing its frames to `sink`, the tracer's handler."""
        run_id = uuid.uuid7().hex
        trace_id = self._trace.trace_id(run_id)
        projector = EventProjector(run_id, trace_id, sink, self._mcp)
        config: RunnableConfig = {
            "configurable": {"thread_id": thread},
            "callbacks": [projector, self._trace.handler(run_id)],
            "metadata": {**self._trace.session(thread), "deeptrack_run_id": run_id},
            "run_name": "deeptrack",
            "recursion_limit": RECURSION,
        }
        return ChatRun(run_id=run_id, trace_id=trace_id, url=self._trace.url(trace_id), config=config), projector

    async def turn(self, thread: str, message: str | Decision, sink: Sink) -> ChatTurn:
        """One run: a user message, or the operator's decision resuming an approval stop; frames go to `sink`."""
        run, projector = self.run(thread, sink)
        try:
            await self._graph.ainvoke(self._turn_input(message), run.config)
        except GuardError as stop:
            return ChatTurn(
                run_id=run.run_id, trace_id=run.trace_id, url=run.url, reply=stop.message, blocked=stop.label
            )
        snapshot = await self._graph.aget_state(run.config)
        stop = next((each.value for each in snapshot.interrupts), None)
        projector.interrupt(stop) if stop is not None else None
        return ChatTurn(
            run_id=run.run_id,
            trace_id=run.trace_id,
            url=run.url,
            reply=self._turn_reply(snapshot.values),
            interrupt=stop,
        )
