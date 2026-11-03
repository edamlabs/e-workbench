"""cli/console: EventConsole — a sink that draws the frames on a terminal: one line per span edge, tokens inline.

Depth comes from the frames themselves (a span sits one level under its parent), color from the kind: the same
two facts a canvas will draw from."""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from rich.console import Console
from rich.markup import escape

from processors.models import EventKind, EventPhase, RunEvent

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
    {EventPhase.START: "▶", EventPhase.END: "■", EventPhase.ERROR: "✖", EventPhase.DELTA: "·"}
)


class EventConsole:
    """Frames as an indented, colored tree; token deltas stream on the line of the model call they belong to."""

    __slots__ = ("_console", "_depth", "_streaming")

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console(highlight=False)
        self._depth: dict[str, int] = {}
        self._streaming = ""

    def _show_line(self, event: RunEvent) -> None:
        depth = self._depth.setdefault(event.id, self._depth.get(event.parent, -1) + 1)
        latency = f" {event.latency_ms:.0f}ms" if event.latency_ms is not None else ""
        detail = escape(str(event.payload)[:160]) if event.payload else ""
        color = COLORS[event.kind]
        self._console.print(
            f"{'  ' * depth}[{color}]{MARKS[event.phase]} {event.kind} {escape(event.name)}[/]"
            f"[dim]{latency} {escape(event.ns)} {detail}[/]"
        )

    def _show_token(self, event: RunEvent) -> None:
        self._console.print(escape(str(event.payload.get("token", ""))), end="", style="dim magenta")

    ############################################################

    def show(self, event: RunEvent) -> None:
        """Draw one frame: a delta continues its line, any other frame closes it and opens its own."""
        match (event.phase, self._streaming == event.id):
            case (EventPhase.DELTA, True):
                self._show_token(event)
            case (EventPhase.DELTA, False):
                self._console.print()
                self._streaming = event.id
                self._show_token(event)
            case _:
                self._console.print() if self._streaming else None
                self._streaming = ""
                self._show_line(event)
