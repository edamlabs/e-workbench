"""instrument.projector: EventProjector — LangChain's callback stream folded into RunEvents, live, in-process.

Every runnable LangChain starts reports its run id and its parent's. The projector keeps the spans a person reads —
the run, the graph nodes (a chain named after its own `langgraph_node`), model calls, tools, MCP tools and
subagents — and folds every other chain (sequences, middleware plumbing) into its nearest kept ancestor, so a
frame's `parent` is always a span that was itself emitted. One run, one projector: `seq` counts its frames. The
sink is whatever consumes them; the projector neither knows nor waits for it."""

import itertools
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGenerationChunk, GenerationChunk, LLMResult
from langgraph.errors import GraphBubbleUp

from deeptrack.models.event import EventKind, EventPhase, RunEvent
from deeptrack.ops.mask import mask_clip, mask_text

type Sink = Callable[[RunEvent], None]

### deepagents launches every subagent through one tool: its name marks the span as a subagent.
TOOL_KINDS: Final[Mapping[str, EventKind]] = MappingProxyType({"task": EventKind.SUBAGENT})


@dataclass(frozen=True, slots=True)
class OpenSpan:
    """A kept span still running: what it is, where it sits, and when it began."""

    kind: EventKind
    name: str
    parent: str
    node: str
    ns: str
    began: float


class EventProjector(AsyncCallbackHandler):
    """One run's callbacks as ordered, parented, masked frames, pushed to a sink as they happen."""

    def __init__(self, run_id: str, trace_id: str, sink: Sink, mcp: frozenset[str] = frozenset()) -> None:
        self._run_id = run_id
        self._trace_id = trace_id
        self._sink = sink
        self._tools: Mapping[str, EventKind] = {**TOOL_KINDS, **dict.fromkeys(mcp, EventKind.MCP)}
        self._seq = itertools.count()
        self._root = ""
        ### every run id seen → the span its children hang from: itself when kept, its kept ancestor when folded.
        self._spans: dict[UUID, str] = {}
        self._open: dict[UUID, OpenSpan] = {}

    def _common_visible(self, parent_run_id: UUID | None) -> str:
        return self._spans.get(parent_run_id, "") if parent_run_id else ""

    def _common_emit(
        self, span_id: str, span: OpenSpan, phase: EventPhase, payload: dict[str, Any], latency: float | None = None
    ) -> None:
        self._sink(
            RunEvent(
                run_id=self._run_id,
                trace_id=self._trace_id,
                seq=next(self._seq),
                id=span_id,
                parent=span.parent,
                kind=span.kind,
                phase=phase,
                name=span.name,
                node=span.node,
                ns=span.ns,
                latency_ms=latency,
                payload=payload,
            )
        )

    def _common_start(
        self,
        run_id: UUID,
        parent_run_id: UUID | None,
        kind: EventKind,
        name: str,
        metadata: dict[str, Any] | None,
        payload: dict[str, Any],
    ) -> None:
        meta = metadata or {}
        span = OpenSpan(
            kind=kind,
            name=name,
            parent=self._common_visible(parent_run_id),
            node=str(meta.get("langgraph_node", "")),
            ns=str(meta.get("checkpoint_ns", "")),
            began=time.perf_counter(),
        )
        self._spans[run_id] = str(run_id)
        self._open[run_id] = span
        self._common_emit(str(run_id), span, EventPhase.START, payload)

    def _common_close(self, run_id: UUID, phase: EventPhase, payload: dict[str, Any]) -> None:
        match self._open.pop(run_id, None):
            case OpenSpan() as span:
                latency = round((time.perf_counter() - span.began) * 1000, 3)
                self._common_emit(str(run_id), span, phase, payload, latency)
            case None:
                pass

    @staticmethod
    def _common_token(token: str | list[str | dict[str, Any]]) -> str:
        """A streamed piece as text: providers with content blocks stream lists of parts."""
        match token:
            case str():
                return token
            case parts:
                return "".join(part if isinstance(part, str) else str(part.get("text", "")) for part in parts)

    def _common_failure(self, run_id: UUID, error: BaseException) -> None:
        ### an interrupt bubbles up as an exception: it is a stop, not a failure.
        match error:
            case GraphBubbleUp():
                self._common_close(run_id, EventPhase.END, {"interrupted": True})
            case _:
                self._common_close(run_id, EventPhase.ERROR, {"error": mask_clip(f"{type(error).__name__}: {error}")})

    ############################################################

    async def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: dict[str, Any] | Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        name = str(kwargs.get("name") or (serialized or {}).get("name", ""))
        ### a compiled subgraph mounted as a node opens a second chain under the node, named like it: one span, not two.
        nested = getattr(self._open.get(parent_run_id) if parent_run_id else None, "name", None) == name
        match (parent_run_id, (metadata or {}).get("langgraph_node") == name and not nested):
            case (None, _):
                self._root = str(run_id)
                self._common_start(run_id, None, EventKind.RUN, name, metadata, {"input": mask_clip(inputs)})
            case (_, True):
                self._common_start(run_id, parent_run_id, EventKind.NODE, name, metadata, {})
            case _:
                self._spans[run_id] = self._common_visible(parent_run_id)

    async def on_chain_end(self, outputs: dict[str, Any] | Any, *, run_id: UUID, **kwargs: Any) -> None:
        keys = sorted(outputs) if isinstance(outputs, dict) else []
        self._common_close(run_id, EventPhase.END, {"keys": keys})

    async def on_chain_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._common_failure(run_id, error)

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any] | None,
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        model = str((metadata or {}).get("ls_model_name") or kwargs.get("name") or "model")
        payload = {"messages": sum(len(batch) for batch in messages)}
        self._common_start(run_id, parent_run_id, EventKind.LLM, model, metadata, payload)

    async def on_llm_new_token(
        self,
        token: str | list[str | dict[str, Any]],
        *,
        chunk: GenerationChunk | ChatGenerationChunk | None = None,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        match (self._common_token(token), self._open.get(run_id)):
            case ("", _) | (_, None):
                pass
            case (text, OpenSpan() as span):
                self._common_emit(str(run_id), span, EventPhase.DELTA, {"token": mask_text(text)})

    async def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        message = getattr(next(itertools.chain.from_iterable(response.generations), None), "message", None)
        payload = {
            "text": mask_clip(getattr(message, "text", "")),
            "tool_calls": [call.get("name", "") for call in getattr(message, "tool_calls", None) or []],
            "usage": dict(getattr(message, "usage_metadata", None) or {}),
        }
        self._common_close(run_id, EventPhase.END, payload)

    async def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._common_failure(run_id, error)

    async def on_tool_start(
        self,
        serialized: dict[str, Any] | None,
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        name = str(kwargs.get("name") or (serialized or {}).get("name") or "tool")
        kind = self._tools.get(name, EventKind.TOOL)
        self._common_start(run_id, parent_run_id, kind, name, metadata, {"input": mask_clip(inputs or input_str)})

    async def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self._common_close(run_id, EventPhase.END, {"output": mask_clip(getattr(output, "content", output))})

    async def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._common_failure(run_id, error)

    def interrupt(self, value: Any) -> None:
        """The run stopped for the operator: one frame under the run, carrying what is asked to approve."""
        span = OpenSpan(kind=EventKind.INTERRUPT, name="approval", parent=self._root, node="approval", ns="", began=0.0)
        self._common_emit(f"{self._root}:interrupt", span, EventPhase.START, {"value": mask_clip(value)})
