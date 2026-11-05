"""providers/adapters/sink/console: ConsoleAdapter — an etrack sink that draws the frames on a terminal: one line per span edge, text inline.

Depth comes from the frames themselves (a span sits one level under its parent), color from the kind: the same two
facts a canvas will draw from. Text and reasoning deltas stream on the line of the model call they belong to; every
other frame closes that line and opens its own."""

from collections.abc import Mapping
from types import MappingProxyType
from typing import ClassVar, Final, Self

from etrack.models.event import EventKind, EventPhase, EventView, Part, RunEvent
from etrack.ports.provider import Isolation, Locality, ProviderSpec, Workload
from rich.console import Console
from rich.markup import escape

COLORS: Final[Mapping[EventKind, str]] = MappingProxyType(
    {
        EventKind.RUN: "bold white",
        EventKind.NODE: "cyan",
        EventKind.LLM: "magenta",
        EventKind.TOOL: "yellow",
        EventKind.MCP: "green",
        EventKind.SUBAGENT: "bold blue",
        EventKind.INTERRUPT: "bold red",
    }
)
MARKS: Final[Mapping[EventPhase, str]] = MappingProxyType(
    {EventPhase.START: "▶", EventPhase.END: "■", EventPhase.ERROR: "✖", EventPhase.DELTA: "·", EventPhase.INSTANT: "◆"}
)
SHOWN: Final[frozenset[Part | None]] = frozenset({Part.TEXT, Part.REASONING})
DETAIL: Final[int] = 160


class ConsoleAdapter:
    """Frames as an indented, colored tree on the terminal."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("console", Locality.EMBEDDED, Workload.IO_BOUND, Isolation.LOOP)
    view: ClassVar[type[EventView]] = RunEvent
    phases: ClassVar[frozenset[EventPhase]] = frozenset(EventPhase)

    __slots__ = ("_console", "_depth", "_streaming")

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console(highlight=False)
        self._depth: dict[str, int] = {}
        self._streaming = ""

    ##### PRIVATE #####

    def _send_line(self, event: RunEvent) -> None:
        depth = self._depth.setdefault(event.id, self._depth.get(event.parent, -1) + 1)
        latency = f" {event.latency_ms:.0f}ms" if event.latency_ms is not None else ""
        detail = escape(str(event.payload)[:DETAIL]) if event.payload else ""
        color = COLORS.get(event.kind, "white")
        self._console.print(
            f"{'  ' * depth}[{color}]{MARKS[event.phase]} {event.kind} {escape(event.name)}[/]"
            f"[dim]{latency} {escape(event.ns)} {detail}[/]"
        )

    def _send_token(self, event: RunEvent) -> None:
        style = "dim magenta" if event.part is Part.TEXT else "dim italic"
        self._console.print(escape(str(event.payload.get("delta", ""))), end="", style=style)

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        _ = self._streaming and self._console.print()

    async def health(self) -> bool:
        """Always ready: the terminal is this process's."""
        return True

    async def send(self, view: EventView) -> None:
        """Draw one frame: a text delta continues its line, any other frame closes it and opens its own."""
        event = RunEvent.project(view)
        match (event.phase, event.part in SHOWN, self._streaming == event.id):
            case (EventPhase.DELTA, False, _):
                pass
            case (EventPhase.DELTA, True, True):
                self._send_token(event)
            case (EventPhase.DELTA, True, False):
                self._console.print()
                self._streaming = event.id
                self._send_token(event)
            case _:
                _ = self._streaming and self._console.print()
                self._streaming = ""
                self._send_line(event)
