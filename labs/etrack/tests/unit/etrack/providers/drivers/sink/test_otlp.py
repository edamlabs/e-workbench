"""tests/unit/etrack/providers/drivers/sink/otlp: frames as spans and logs — derived ids, nesting, dialects, closure."""

from datetime import timedelta
from typing import TYPE_CHECKING, Any

import pytest
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from etrack.infra.config.base import Secret
from etrack.infra.config.providers.drivers.sink.otlp import OtlpSettings, OtlpTarget
from etrack.infra.errors import SinkError
from etrack.models.event import EventKind, EventPhase, Failure, ModelRef, Part, Usage
from etrack.ports.sink import SinkPort
from etrack.providers.drivers.sink.otlp import OtlpDriver
from support.collector import fake_collector
from unit.etrack.conftest import RUN, frame

if TYPE_CHECKING:
    from pytest_httpserver import HTTPServer

ROOT = RUN
CHILD = "0" * 16 + "a" * 16


@pytest.fixture
def spans() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
def logs() -> InMemoryLogRecordExporter:
    return InMemoryLogRecordExporter()


async def run_tree(driver: OtlpDriver) -> None:
    await driver.send(frame(0, EventPhase.START, id=ROOT, kind=EventKind.RUN, name="deeptrack"))
    await driver.send(
        frame(
            1,
            EventPhase.START,
            id=CHILD,
            parent=ROOT,
            kind=EventKind.LLM,
            name="gemini",
            model=ModelRef(provider="google", name="gemini-2.5-flash", params={"temperature": 0.1}),
            payload={"input": [{"role": "human", "content": "hi"}]},
        )
    )
    await driver.send(
        frame(
            2,
            EventPhase.END,
            id=CHILD,
            parent=ROOT,
            kind=EventKind.LLM,
            name="gemini",
            usage=Usage(input_tokens=3, output_tokens=4, total_tokens=7),
            payload={"text": "hola"},
        )
    )
    await driver.send(frame(3, EventPhase.END, id=ROOT, kind=EventKind.RUN, name="deeptrack"))


async def test_otlp_meets_port(spans: InMemorySpanExporter) -> None:
    assert isinstance(OtlpDriver(span_exporters=[spans]), SinkPort)


async def test_otlp_framework_payload_encoded(spans: InMemorySpanExporter) -> None:
    message = ToolMessage("seg:Poliza", tool_call_id="c1")
    async with OtlpDriver(span_exporters=[spans]) as driver:
        await driver.send(
            frame(0, EventPhase.START, id=ROOT, kind=EventKind.TOOL, name="t", payload={"input": message})
        )
        await driver.send(frame(1, EventPhase.END, id=ROOT, kind=EventKind.TOOL, name="t", payload={"output": message}))
    (span,) = spans.get_finished_spans()
    attributes = dict(span.attributes or {})
    assert '"tool_call_id":"c1"' in str(attributes["input.value"])
    assert '"content":"seg:Poliza"' in str(attributes["output.value"])


async def test_otlp_dataclass_payload_encoded() -> None:
    assert '"goto":"gate"' in str(OtlpDriver._common_flat(Command(goto="gate")))


async def test_otlp_ids_derived(spans: InMemorySpanExporter) -> None:
    async with OtlpDriver(span_exporters=[spans]) as driver:
        await run_tree(driver)
    finished = {span.name: span for span in spans.get_finished_spans()}
    assert {span.context.trace_id for span in finished.values()} == {int(RUN, 16)}
    assert finished["gemini"].context.span_id == int("a" * 16, 16)
    assert finished["gemini"].parent is not None
    assert finished["gemini"].parent.span_id == finished["deeptrack"].context.span_id


async def test_otlp_dialects(spans: InMemorySpanExporter) -> None:
    async with OtlpDriver(span_exporters=[spans]) as driver:
        await run_tree(driver)
    llm = {span.name: span for span in spans.get_finished_spans()}["gemini"]
    attributes: dict[str, Any] = dict(llm.attributes or {})
    assert attributes["gen_ai.operation.name"] == "chat"
    assert attributes["gen_ai.request.model"] == "gemini-2.5-flash"
    assert attributes["gen_ai.request.temperature"] == 0.1
    assert attributes["gen_ai.usage.input_tokens"] == 3
    assert attributes["openinference.span.kind"] == "LLM"
    assert attributes["llm.token_count.total"] == 7
    assert attributes["langfuse.observation.type"] == "generation"
    assert attributes["langfuse.session.id"] == "t1"
    assert attributes["input.value"] == '[{"role":"human","content":"hi"}]'
    assert attributes["output.value"] == '{"text":"hola"}'
    assert llm.status.status_code is StatusCode.OK


async def test_otlp_error_status(spans: InMemorySpanExporter) -> None:
    async with OtlpDriver(span_exporters=[spans]) as driver:
        await driver.send(frame(0, EventPhase.START, id=ROOT, kind=EventKind.TOOL, name="t"))
        await driver.send(
            frame(
                1,
                EventPhase.ERROR,
                id=ROOT,
                kind=EventKind.TOOL,
                name="t",
                error=Failure(type="ValueError", message="x"),
            )
        )
    (span,) = spans.get_finished_spans()
    assert span.status.status_code is StatusCode.ERROR
    assert dict(span.attributes or {})["exception.type"] == "ValueError"


async def test_otlp_instant_under_closed_parent(spans: InMemorySpanExporter) -> None:
    async with OtlpDriver(span_exporters=[spans]) as driver:
        await driver.send(frame(0, EventPhase.START, id=ROOT, kind=EventKind.RUN, name="run"))
        await driver.send(frame(1, EventPhase.START, id=CHILD, parent=ROOT, name="ask"))
        await driver.send(frame(2, EventPhase.END, id=CHILD, parent=ROOT, name="ask"))
        await driver.send(
            frame(3, EventPhase.INSTANT, id="stop", parent=CHILD, kind=EventKind.INTERRUPT, name="interrupt")
        )
    finished = {span.name: span for span in spans.get_finished_spans()}
    assert finished["interrupt"].parent is not None
    assert finished["interrupt"].parent.span_id == finished["ask"].context.span_id
    assert "run" in finished  # an unclosed root is ended on exit


async def test_otlp_traces_off(spans: InMemorySpanExporter) -> None:
    async with OtlpDriver(OtlpSettings(traces=False), span_exporters=[spans]) as driver:
        await run_tree(driver)
    assert spans.get_finished_spans() == ()


async def test_otlp_logs(spans: InMemorySpanExporter, logs: InMemoryLogRecordExporter) -> None:
    async with OtlpDriver(span_exporters=[spans], log_exporters=[logs]) as driver:
        await run_tree(driver)
        assert await driver.flush()
    records = [data.log_record for data in logs.get_finished_logs()]
    assert [record.event_name for record in records][:2] == ["etrack.run.start", "etrack.llm.start"]
    assert {record.trace_id for record in records} == {int(RUN, 16)}


async def test_otlp_host_processor(logs: InMemoryLogRecordExporter) -> None:
    async with OtlpDriver(log_exporters=[logs]) as driver:
        processor = driver.processor()
        returned = processor(None, "warning", {"event": "chat open", "driver": "gemini", "gone": None})
        assert await driver.flush()
    assert returned == {"event": "chat open", "driver": "gemini", "gone": None}
    (record,) = [data.log_record for data in logs.get_finished_logs()]
    assert (record.body, record.severity_text, dict(record.attributes or {})) == (
        "chat open",
        "warning",
        {"driver": "gemini"},
    )


async def test_otlp_host_processor_closed() -> None:
    assert OtlpDriver().processor()(None, "info", {"event": "x"}) == {"event": "x"}


async def test_otlp_closed_send() -> None:
    with pytest.raises(SinkError, match="not open"):
        await OtlpDriver().send(frame())


async def test_otlp_health(spans: InMemorySpanExporter) -> None:
    driver = OtlpDriver(span_exporters=[spans])
    assert not await driver.health()
    async with driver:
        assert await driver.health()


async def test_otlp_remote_fake_collector(httpserver: HTTPServer) -> None:
    collector = fake_collector(httpserver)
    target = OtlpTarget(endpoint=f"{collector.endpoint}/", headers={"Authorization": Secret("Basic eA==")})
    settings = OtlpSettings(targets={"fake": target}, logs=True, flush=timedelta(milliseconds=10))
    async with OtlpDriver(settings) as driver:
        await run_tree(driver)
        assert await driver.flush()
    received = {span.name: span for span in collector.spans()}
    assert set(received) == {"deeptrack", "gemini"}
    assert received["gemini"].trace_id == bytes.fromhex(RUN)
    assert received["gemini"].parent_span_id == received["deeptrack"].span_id
    assert all(headers["Authorization"] == "Basic eA==" for headers in collector.headers)
    assert (
        sum(
            len(scope.log_records)
            for request in collector.logs
            for resource in request.resource_logs
            for scope in resource.scope_logs
        )
        == 4
    )


async def test_otlp_delta_is_logged_not_spanned(spans: InMemorySpanExporter, logs: InMemoryLogRecordExporter) -> None:
    async with OtlpDriver(span_exporters=[spans], log_exporters=[logs]) as driver:
        await driver.send(frame(0, EventPhase.DELTA, id=ROOT, kind=EventKind.LLM, part=Part.TEXT))
        assert await driver.flush()
    assert spans.get_finished_spans() == ()
    assert [data.log_record.event_name for data in logs.get_finished_logs()] == ["etrack.llm.delta"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("a", "a"),
        (1, 1),
        (True, True),
        (0.5, 0.5),
        ({"a": [1]}, '{"a":[1]}'),
        ({"a": Ellipsis}, '{"a":"Ellipsis"}'),
    ],
    ids=["str", "int", "bool", "float", "json", "unknown"],
)
async def test_otlp_flat(value: Any, expected: Any) -> None:
    assert OtlpDriver._common_flat(value) == expected
