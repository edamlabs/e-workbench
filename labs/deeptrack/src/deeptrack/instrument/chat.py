"""instrument.chat: TracedChat — one chat turn over the outer graph, seen live by the projector and kept by Langfuse.

A turn is a run: a fresh run id, its derived trace id, a projector pushing frames to the sink and Langfuse's handler
on the same callbacks. The thread id is the conversation (the checkpointer's key, Langfuse's session). After the
graph returns, the checkpoint says whether it stopped for approval: deterministic, no stream parsing."""

import uuid
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from deeptrack.adapters.trace import TraceAdapter
from deeptrack.instrument.projector import EventProjector, Sink
from deeptrack.models.proposal import Decision
from deeptrack.models.turn import ChatTurn

RECURSION: int = 120


class TracedChat:
    """The outer graph, its tracer, the live sink, and the MCP tool names that tell MCP spans apart."""

    __slots__ = ("_graph", "_mcp", "_sink", "_trace")

    def __init__(self, graph: CompiledStateGraph, trace: TraceAdapter, sink: Sink, mcp: frozenset[str]) -> None:
        self._graph = graph
        self._trace = trace
        self._sink = sink
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

    async def turn(self, thread: str, message: str | Decision) -> ChatTurn:
        """One run: a user message, or the operator's decision resuming an approval stop."""
        run_id = uuid.uuid7().hex
        trace_id = self._trace.trace_id(run_id)
        projector = EventProjector(run_id, trace_id, self._sink, self._mcp)
        config: RunnableConfig = {
            "configurable": {"thread_id": thread},
            "callbacks": [projector, self._trace.handler(run_id)],
            "metadata": {"langfuse_session_id": thread, "deeptrack_run_id": run_id},
            "run_name": "deeptrack",
            "recursion_limit": RECURSION,
        }
        await self._graph.ainvoke(self._turn_input(message), config)
        snapshot = await self._graph.aget_state(config)
        stop = next((each.value for each in snapshot.interrupts), None)
        projector.interrupt(stop) if stop is not None else None
        return ChatTurn(
            run_id=run_id,
            trace_id=trace_id,
            url=self._trace.url(trace_id),
            reply=self._turn_reply(snapshot.values),
            interrupt=stop,
        )
