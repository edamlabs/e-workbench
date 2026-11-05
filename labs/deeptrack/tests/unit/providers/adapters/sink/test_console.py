"""providers/adapters/sink/console: the tree drawn by kind and phase, nested by parent, text and reasoning streamed inline."""

from io import StringIO

from etrack.models.event import EventKind, EventPhase, Part
from etrack.ports.sink import SinkPort
from rich.console import Console

from providers.adapters.sink.console import ConsoleAdapter
from tests.unit.providers.adapters.sink.conftest import Frame


async def test_console_meets_sink_port() -> None:
    async with ConsoleAdapter() as console:
        assert isinstance(console, SinkPort)
        assert await console.health()


async def test_console_draws_a_tree(frame: Frame) -> None:
    out = StringIO()
    async with ConsoleAdapter(Console(file=out, width=200, color_system=None)) as view:
        _ = [
            await view.send(each)
            for each in (
                frame(0, "run", "", EventKind.RUN, EventPhase.START),
                frame(1, "node", "run", EventKind.NODE, EventPhase.START),
                frame(2, "llm", "node", EventKind.LLM, EventPhase.START),
                frame(
                    3, "llm", "node", EventKind.LLM, EventPhase.DELTA, part=Part.REASONING, payload={"delta": "pienso "}
                ),
                frame(4, "llm", "node", EventKind.LLM, EventPhase.DELTA, part=Part.TEXT, payload={"delta": "Hol"}),
                frame(5, "llm", "node", EventKind.LLM, EventPhase.DELTA, part=Part.TEXT, payload={"delta": "a"}),
                frame(6, "llm", "node", EventKind.LLM, EventPhase.DELTA, part=Part.TOOL_CALL, payload={"delta": "{}"}),
                frame(7, "llm", "node", EventKind.LLM, EventPhase.END),
                frame(8, "mcp", "node", EventKind.MCP, EventPhase.ERROR, payload={"error": "x"}),
                frame(9, "run:interrupt", "run", EventKind.INTERRUPT, EventPhase.INSTANT),
                frame(10, "ret", "node", EventKind.RETRIEVAL, EventPhase.START),
                frame(11, "llm2", "node", EventKind.LLM, EventPhase.DELTA, part=Part.TEXT, payload={"delta": "fin"}),
            )
        ]
    lines = out.getvalue().splitlines()
    assert lines[0].startswith("▶ run")
    assert lines[1].startswith("  ▶ node")
    assert lines[2].startswith("    ▶ llm")
    assert "pienso Hola" in out.getvalue()
    assert "{}" not in out.getvalue()
    assert any(line.startswith("    ✖ mcp") for line in lines)
    assert any(line.startswith("  ◆ interrupt") for line in lines)
    assert any(line.startswith("    ▶ retrieval") for line in lines)
