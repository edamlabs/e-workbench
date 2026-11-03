"""tests/integration/etrack/providers/drivers/sink/otlp: a real deep-agent run, end to end, into the sandbox collector.

`make stack` brings the collector up (OTLP/HTTP :28120, health :28121) writing what it receives to `.sandbox/` as
OTLP/JSON; the run goes source → fold → channel → bus → live + otlp, and the test reads the collector's files back by
the run's trace id. With no collector answering, the tier skips and says why."""

import json
import urllib.request
from pathlib import Path
from typing import Any, Final

import anyio
import pytest
from deepagents import create_deep_agent
from langchain_core.tools import tool

from etrack.infra.config.providers.drivers.sink.otlp import OtlpSettings, OtlpTarget
from etrack.logic.api import Tracker
from etrack.logic.channel import EventChannel
from etrack.models.event import EventKind
from etrack.providers.adapters.bus.anyio import AnyioBusAdapter
from etrack.providers.adapters.sink.live import LiveSinkAdapter
from etrack.providers.adapters.source.langgraph import LanggraphSourceAdapter
from etrack.providers.drivers.sink.otlp import OtlpDriver
from support.model import call, script

ENDPOINT: Final[str] = "http://127.0.0.1:28120"
HEALTH: Final[str] = "http://127.0.0.1:28121/"
OUT: Final[Path] = Path(__file__).resolve().parents[6] / ".sandbox"
WAIT: Final[float] = 10.0


def answering() -> bool:
    """Whether the sandbox collector is up — read once, at collection."""
    try:
        with urllib.request.urlopen(HEALTH, timeout=1) as reply:
            return reply.status == 200
    except OSError:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not answering(), reason="the sandbox collector does not answer: `make stack` first"),
]


async def received(name: str, trace: str, key: str, items: str) -> list[dict[str, Any]]:
    """Every OTLP/JSON item of one trace the collector wrote to `name`, waiting until some arrive."""
    path = anyio.Path(OUT / name)
    with anyio.fail_after(WAIT):
        ### the collector writes on its own clock: the file is read until the run shows up in it.
        while True:
            lines = (await path.read_text()).splitlines() if await path.exists() else []
            found = [
                item
                for line in lines
                for resource in json.loads(line)[f"resource{key}"]
                for scope in resource[f"scope{key}"]
                for item in scope[items]
                if item.get("traceId") == trace
            ]
            if found:
                return found
            await anyio.sleep(0.2)


async def test_otlp_deep_agent_end_to_end() -> None:
    @tool
    def onto_query(query: str) -> str:
        """Run a SPARQL query."""
        return "seg:Poliza"

    agent = create_deep_agent(
        model=script(
            call("task", "c1", subagent_type="ontologo", description="resuelve Poliza"),
            call("onto_query", "c2", query="SELECT *"),
            "Poliza es seg:Poliza",
            "listo",
        ),
        subagents=[
            {"name": "ontologo", "description": "ontología", "system_prompt": "ontólogo", "tools": [onto_query]}
        ],
    )
    settings = OtlpSettings(targets={"sandbox": OtlpTarget(endpoint=ENDPOINT)}, logs=True, service="etrack-e2e")
    async with LiveSinkAdapter() as live, OtlpDriver(settings) as otlp:
        bus = AnyioBusAdapter()
        bus.subscribe(live)
        bus.subscribe(otlp)
        async with bus:
            tracker = Tracker(EventChannel(bus, forward=None), LanggraphSourceAdapter(mcp=frozenset({"onto_query"})))
            with tracker.track("e2e", {}) as run:
                await agent.ainvoke({"messages": [("user", "¿qué es una póliza?")]}, run.config, stream_mode="messages")
        assert bus.dropped == {}
        assert bus.failed == {}
        kept = live.offset("e2e")
    trace = run.scope.run_id
    spans = await received("traces.jsonl", trace, "Spans", "spans")
    names = {span["name"] for span in spans}
    assert {"ontologo", "onto_query"} <= names
    ids = {span["spanId"] for span in spans}
    (root,) = [span for span in spans if not span.get("parentSpanId")]
    assert all(span["parentSpanId"] in ids for span in spans if span is not root)
    kinds = {
        attribute["value"]["stringValue"]
        for span in spans
        for attribute in span["attributes"]
        if attribute["key"] == "etrack.kind"
    }
    assert {str(EventKind.RUN), str(EventKind.SUBAGENT), str(EventKind.MCP), str(EventKind.LLM)} <= kinds
    logs = await received("logs.jsonl", trace, "Logs", "logRecords")
    assert len(logs) >= len(spans)
    assert kept > len(spans)  # the live sink took every phase, deltas included
