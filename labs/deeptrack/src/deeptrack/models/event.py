"""models.event: RunEvent — the one frame the live stream reads, correlated with the trace Langfuse keeps.

A run is a tree of spans: the run, each graph node, and inside a node every LLM call, tool, MCP call and subagent
the deep agent makes. A frame names its span (`id`, LangChain's run id) and its visible parent, so a consumer
rebuilds the tree without knowing LangGraph; `seq` orders the frames of one run; `trace_id` is the Langfuse trace
the same run lands in. The state decides, the frames show: nothing here is ever read back by the graph."""

from datetime import UTC, datetime
from enum import StrEnum, auto
from typing import Any

import msgspec


class EventKind(StrEnum):
    """What a span is: the run, a graph node, a model call, a plain tool, an MCP tool, a subagent, an approval stop."""

    RUN = auto()
    NODE = auto()
    LLM = auto()
    TOOL = auto()
    MCP = auto()
    SUBAGENT = auto()
    INTERRUPT = auto()


class EventPhase(StrEnum):
    """Where a span is in its life: opened, streaming a piece, closed, or failed."""

    START = auto()
    DELTA = auto()
    END = auto()
    ERROR = auto()


class RunEvent(msgspec.Struct, frozen=True, kw_only=True):
    """One frame: which run and trace, its order, which span and parent, what it is, and its masked payload.

    `node` is the LangGraph node the span runs under and `ns` its checkpoint namespace — the subgraph path a
    subagent's spans carry. `latency_ms` is set on END and ERROR only."""

    run_id: str
    trace_id: str
    seq: int
    id: str
    parent: str = ""
    kind: EventKind
    phase: EventPhase
    name: str
    node: str = ""
    ns: str = ""
    at: datetime = msgspec.field(default_factory=lambda: datetime.now(UTC))
    latency_ms: float | None = None
    payload: dict[str, Any] = msgspec.field(default_factory=dict)
