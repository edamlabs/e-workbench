"""processors/fold: FoldProcessor — a source's edges folded into ordered, parented, stamped RunEvents for one run.

A source reports every span it sees; the fold keeps the ones a person reads (an edge with a `kind`) and folds
plumbing (`kind=None`) into its nearest kept ancestor, so a frame's `parent` is always a span that was itself emitted.
It stamps what the source cannot know: the run's ids, `seq`, the `visit` count of each node, the latency of a closed
span, and the payload passed through the project's `redact`. One fold per run; `emit` is whoever takes the frames."""

import itertools
import time
import uuid
from collections import Counter
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Final

from etrack.models.event import EventKind, EventPhase, Failure, Part, RunEvent, RunScope, Usage
from etrack.ports.source import Edge

type Emit = Callable[[RunEvent], None]
type Redact = Callable[[dict[str, Any]], dict[str, Any]]

MS: Final[float] = 1000.0


@dataclass(frozen=True, slots=True)
class OpenSpan:
    """A kept span still running: the edge it opened with, its visible parent, its visit and when it began."""

    edge: Edge
    parent: str
    visit: int | None
    began: float


class FoldProcessor:
    """One run's edges as frames, pushed to `emit` the moment they are folded."""

    __slots__ = ("_emit", "_open", "_redact", "_root", "_scope", "_seq", "_spans", "_visits")

    def __init__(self, scope: RunScope, emit: Emit, redact: Redact | None = None) -> None:
        self._scope = scope
        self._emit = emit
        self._redact = redact or self._common_keep
        self._seq = itertools.count()
        self._root = ""
        ### every id seen → the span its children hang from: itself when kept, its kept ancestor when folded.
        self._spans: dict[str, str] = {}
        self._open: dict[str, OpenSpan] = {}
        self._visits: Counter[str] = Counter()

    ##### PRIVATE #####

    @staticmethod
    def _common_keep(payload: dict[str, Any]) -> dict[str, Any]:
        """The default redaction: the payload untouched."""
        return payload

    def _common_visible(self, parent: str) -> str:
        return self._spans.get(parent, self._root if parent else "")

    def _common_visit(self, edge: Edge) -> int | None:
        match edge.kind:
            case EventKind.NODE:
                self._visits[edge.name] += 1
                return self._visits[edge.name]
            case _:
                return None

    def _common_frame(
        self,
        span: OpenSpan,
        phase: EventPhase,
        payload: dict[str, Any],
        **fields: Any,
    ) -> None:
        edge = span.edge
        self._emit(
            RunEvent(
                run_id=self._scope.run_id,
                thread_id=self._scope.thread_id,
                seq=next(self._seq),
                id=edge.id,
                parent=span.parent,
                kind=edge.kind or EventKind.CUSTOM,
                phase=phase,
                name=edge.name,
                node=edge.node,
                ns=edge.ns,
                step=edge.step,
                visit=span.visit,
                ### an LLM call's message id is its span: every delta of one call belongs to one chat message.
                message_id=edge.message_id or (edge.id if edge.kind is EventKind.LLM else ""),
                call_id=fields.pop("call_id", "") or edge.call_id,
                model=edge.model,
                payload=self._redact(payload),
                attributes=edge.attributes,
                **fields,
            )
        )

    ############################################################

    ##### PUBLIC #####

    @property
    def scope(self) -> RunScope:
        """The run this fold stamps."""
        return self._scope

    @property
    def root(self) -> str:
        """The id of the run's root span, empty until the first kept span opens."""
        return self._root

    def open(self, edge: Edge) -> None:
        """A span begins: emitted when kept, folded into its ancestor when plumbing."""
        parent = self._common_visible(edge.parent)
        match edge.kind:
            case None:
                self._spans[edge.id] = parent
            case _:
                self._root = self._root or edge.id
                span = OpenSpan(edge=edge, parent=parent, visit=self._common_visit(edge), began=time.perf_counter())
                self._spans[edge.id] = edge.id
                self._open[edge.id] = span
                self._common_frame(span, EventPhase.START, edge.payload)

    def delta(self, span: str, part: Part, payload: dict[str, Any], call_id: str = "") -> None:
        """A streamed piece of an open span; a piece of a span never opened, or already closed, is dropped."""
        match self._open.get(span):
            case OpenSpan() as opened:
                self._common_frame(opened, EventPhase.DELTA, payload, part=part, call_id=call_id)
            case _:
                pass

    def close(
        self, span: str, payload: dict[str, Any], usage: Usage | None = None, error: Failure | None = None
    ) -> None:
        """A span ends — END, or ERROR when it carries a failure; closing a folded or unknown span does nothing."""
        match self._open.pop(span, None):
            case OpenSpan() as opened:
                latency = round((time.perf_counter() - opened.began) * MS, 3)
                phase = EventPhase.END if error is None else EventPhase.ERROR
                self._common_frame(opened, phase, payload, latency_ms=latency, usage=usage, error=error)
            case _:
                pass

    def instant(self, edge: Edge) -> None:
        """A frame born closed — an interrupt, a state, a score, a custom fact — under its visible parent."""
        parent = self._common_visible(edge.parent) if edge.parent else self._root
        span = OpenSpan(edge=edge, parent=parent, visit=None, began=time.perf_counter())
        self._common_frame(span, EventPhase.INSTANT, edge.payload)

    @contextmanager
    def span(
        self, name: str, kind: EventKind = EventKind.CUSTOM, parent: str = "", payload: dict[str, Any] | None = None
    ) -> Generator[str]:
        """A span around a block of the project's own code: START on entry, END or ERROR on exit; yields its id."""
        span = uuid.uuid7().hex
        self.open(Edge(id=span, parent=parent or self._root, kind=kind, name=name, payload=payload or {}))
        try:
            yield span
        except BaseException as failure:
            self.close(span, {}, error=Failure(type=type(failure).__name__, message=str(failure)))
            raise
        self.close(span, {})
