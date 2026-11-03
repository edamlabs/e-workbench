"""The console sink draws every kind and phase, nests by parent, and streams deltas on one line."""

from io import StringIO

from rich.console import Console

from deeptrack.cli.console import EventConsole
from processors.models import EventKind, EventPhase, RunEvent


def frame(seq: int, span: str, parent: str, kind: EventKind, phase: EventPhase, **payload: object) -> RunEvent:
    return RunEvent(
        run_id="r",
        trace_id="t",
        seq=seq,
        id=span,
        parent=parent,
        kind=kind,
        phase=phase,
        name=str(kind),
        payload=dict(payload),
    )


def test_console_draws_a_tree() -> None:
    out = StringIO()
    view = EventConsole(Console(file=out, width=200, color_system=None))
    [
        view.show(each)
        for each in (
            frame(0, "run", "", EventKind.RUN, EventPhase.START),
            frame(1, "node", "run", EventKind.NODE, EventPhase.START),
            frame(2, "llm", "node", EventKind.LLM, EventPhase.START),
            frame(3, "llm", "node", EventKind.LLM, EventPhase.DELTA, token="Hol"),
            frame(4, "llm", "node", EventKind.LLM, EventPhase.DELTA, token="a"),
            frame(5, "llm", "node", EventKind.LLM, EventPhase.END),
            frame(6, "mcp", "node", EventKind.MCP, EventPhase.ERROR, error="x"),
            frame(7, "run:interrupt", "run", EventKind.INTERRUPT, EventPhase.START),
        )
    ]
    lines = out.getvalue().splitlines()
    assert lines[0].startswith("▶ run")
    assert lines[1].startswith("  ▶ node")
    assert lines[2].startswith("    ▶ llm")
    assert "Hola" in out.getvalue()
    assert any(line.startswith("    ✖ mcp") for line in lines)
    assert any(line.startswith("  ▶ interrupt") for line in lines)
