"""models/event: RunEvent — the one record every source writes and every client reads, and the views that narrow it.

A run is a tree of spans. A frame names its span (`id`) and its visible `parent`, so any client rebuilds the tree
without knowing the framework that produced it; `seq` orders the frames of one run. The two axes say what happened:
`kind` is what the span is (aligned with OpenTelemetry's GenAI operations and AG-UI's agent concepts), `phase` where
it is in its life; `part` says what a streamed piece carries (text, reasoning, a tool call's arguments, media).

The field names are the reserved keys of the log channel. The record grows two ways and never breaks: optional typed
sections (`model`, `usage`, `error`) and the open `attributes` bag, namespaced by its consumer (`agui.*`, `app.*`); a
project that needs more subclasses `RunEvent` and hands the subclass to the channel. A client never reads the record
whole: it declares an `EventView` with the fields it needs and `project` narrows any event onto it."""

from datetime import UTC, datetime
from enum import StrEnum, auto
from typing import Any, Final, Self

import msgspec

VERSION: Final[int] = 1


##### AXES #####
class EventKind(StrEnum):
    """What a span is. `CUSTOM` is the fallback for whatever a source or a project names that no other kind covers."""

    RUN = auto()
    AGENT = auto()
    SUBAGENT = auto()
    NODE = auto()
    LLM = auto()
    EMBEDDING = auto()
    RETRIEVAL = auto()
    TOOL = auto()
    MCP = auto()
    INTERRUPT = auto()
    STATE = auto()
    EVALUATION = auto()
    CUSTOM = auto()


class EventPhase(StrEnum):
    """Where a span is in its life; `INSTANT` is a span that is born and closed at once (an interrupt, a state, a score)."""

    START = auto()
    DELTA = auto()
    END = auto()
    ERROR = auto()
    INSTANT = auto()


class Part(StrEnum):
    """What a streamed piece carries — LangChain's v1 content blocks, AG-UI's message kinds; `CUSTOM` for the rest."""

    TEXT = auto()
    REASONING = auto()
    TOOL_CALL = auto()
    IMAGE = auto()
    AUDIO = auto()
    VIDEO = auto()
    FILE = auto()
    CUSTOM = auto()


##### SECTIONS #####
class Usage(msgspec.Struct, frozen=True, kw_only=True):
    """Tokens a model call spent, by kind, and its cost when the source knows it."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float | None = None


class ModelRef(msgspec.Struct, frozen=True, kw_only=True):
    """Which model served a call: the provider, the model's name, and the request parameters worth keeping."""

    provider: str = ""
    name: str = ""
    params: dict[str, Any] = msgspec.field(default_factory=dict)


class Failure(msgspec.Struct, frozen=True, kw_only=True):
    """Why a span failed: the exception's type and its message."""

    type: str
    message: str = ""


class RunScope(msgspec.Struct, frozen=True, kw_only=True):
    """One run before its first frame: its id (32 hex, the trace id too) and the conversation it belongs to."""

    run_id: str
    thread_id: str = ""


##### VIEWS #####
class EventView(msgspec.Struct, frozen=True, kw_only=True):
    """The base of every view a client declares: a subset of the record's fields, same names, same types."""

    @classmethod
    def project(cls, event: EventView) -> Self:
        """Any event narrowed onto this view — fields this view does not declare are left behind."""
        return msgspec.convert(event, cls, from_attributes=True)


##### RECORD #####
class RunEvent(EventView, frozen=True, kw_only=True):
    """One frame of a run: who, where in the tree, what and when, and what it carried.

    `node`, `ns` and `step` are the graph coordinates when the source has a graph (the node a span runs under, its
    subgraph path, the superstep); `visit` counts how many times the run has entered that node. `message_id` and
    `call_id` tie a frame to the chat message or the tool call a client renders. `latency_ms` is set on END and ERROR."""

    v: int = VERSION
    run_id: str
    thread_id: str = ""
    seq: int
    id: str
    parent: str = ""
    kind: EventKind
    phase: EventPhase
    name: str = ""
    node: str = ""
    ns: str = ""
    step: int | None = None
    visit: int | None = None
    part: Part | None = None
    message_id: str = ""
    call_id: str = ""
    at: datetime = msgspec.field(default_factory=lambda: datetime.now(UTC))
    latency_ms: float | None = None
    model: ModelRef | None = None
    usage: Usage | None = None
    error: Failure | None = None
    payload: dict[str, Any] = msgspec.field(default_factory=dict)
    attributes: dict[str, Any] = msgspec.field(default_factory=dict)

    @property
    def trace_id(self) -> str:
        """The W3C trace id of the run: the run id itself, so every tracer names the run the same way."""
        return self.run_id

    @property
    def dedupe_key(self) -> str:
        """What makes a frame unique across redeliveries: its run, its span and the edge of the span it marks."""
        return f"{self.run_id}:{self.id}:{self.phase}:{self.seq}"


class LogView(EventView, frozen=True, kw_only=True):
    """What a log line keeps of a frame: the coordinates and the measures, never the payload."""

    run_id: str
    thread_id: str = ""
    seq: int
    id: str
    parent: str = ""
    kind: EventKind
    phase: EventPhase
    name: str = ""
    node: str = ""
    step: int | None = None
    part: Part | None = None
    latency_ms: float | None = None
    usage: Usage | None = None
    error: Failure | None = None
