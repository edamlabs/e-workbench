"""providers/drivers/sink/otlp: OtlpDriver — frames as OpenTelemetry spans and logs, exported over OTLP/HTTP.

A START opens a span, its END or ERROR closes it at the frame's own time; an INSTANT is a span born closed. Ids are
derived, never minted: the trace id is the run id and a span id the low 64 bits of the frame's id, so the same run
and the same span carry the same names in every backend and in the live stream. Each span speaks three dialects at
once — OpenTelemetry GenAI (`gen_ai.*`), OpenInference (`openinference.span.kind`, `input.value`, `llm.*`) and
Langfuse's keys (`langfuse.observation.type`, `langfuse.session.id`) — each backend reads what it knows. Every
collector in `targets` receives everything; none set, spans are still minted and dropped. With `logs`, each frame is
also a log record on its span; `processor` hands the host a structlog processor that does the same for its own logs.
The driver owns a private `TracerProvider` and `LoggerProvider`, never the process-global ones."""

import asyncio
from datetime import datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar, Final, Self

import eserde
import msgspec
from opentelemetry import trace
from opentelemetry._logs import Logger, LogRecord, SeverityNumber
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, LogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.id_generator import IdGenerator, RandomIdGenerator
from opentelemetry.trace import NonRecordingSpan, SpanContext, Status, StatusCode, TraceFlags

from etrack.infra.errors import SinkError
from etrack.infra.logger import logger
from etrack.infra.settings import settings as st
from etrack.models.event import EventKind, EventPhase, EventView, Failure, ModelRef, Part, Usage
from etrack.ops.w3c import w3c_span, w3c_trace
from etrack.ports.provider import Isolation, Locality, ProviderSpec, Workload

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from opentelemetry.trace import Span, Tracer

    from etrack.infra.config.providers.drivers.sink.otlp import OtlpSettings

type Primitive = str | bool | int | float

NS: Final[int] = 1_000_000_000
MS: Final[float] = 1000.0
PHASES: Final[frozenset[EventPhase]] = frozenset(
    {EventPhase.START, EventPhase.END, EventPhase.ERROR, EventPhase.INSTANT}
)
OPERATIONS: Final[Mapping[EventKind, str]] = MappingProxyType(
    {
        EventKind.RUN: "invoke_workflow",
        EventKind.AGENT: "invoke_agent",
        EventKind.SUBAGENT: "invoke_agent",
        EventKind.LLM: "chat",
        EventKind.EMBEDDING: "embeddings",
        EventKind.RETRIEVAL: "retrieval",
        EventKind.TOOL: "execute_tool",
        EventKind.MCP: "execute_tool",
    }
)
OPENINFERENCE: Final[Mapping[EventKind, str]] = MappingProxyType(
    {
        EventKind.AGENT: "AGENT",
        EventKind.SUBAGENT: "AGENT",
        EventKind.LLM: "LLM",
        EventKind.EMBEDDING: "EMBEDDING",
        EventKind.RETRIEVAL: "RETRIEVER",
        EventKind.TOOL: "TOOL",
        EventKind.MCP: "TOOL",
        EventKind.EVALUATION: "EVALUATOR",
    }
)
LANGFUSE: Final[Mapping[EventKind, str]] = MappingProxyType(
    {
        EventKind.RUN: "chain",
        EventKind.NODE: "chain",
        EventKind.AGENT: "agent",
        EventKind.SUBAGENT: "agent",
        EventKind.LLM: "generation",
        EventKind.EMBEDDING: "embedding",
        EventKind.RETRIEVAL: "retriever",
        EventKind.TOOL: "tool",
        EventKind.MCP: "tool",
        EventKind.EVALUATION: "evaluator",
    }
)
SEVERITIES: Final[Mapping[EventPhase, SeverityNumber]] = MappingProxyType(
    {
        EventPhase.START: SeverityNumber.INFO,
        EventPhase.DELTA: SeverityNumber.DEBUG,
        EventPhase.END: SeverityNumber.INFO,
        EventPhase.ERROR: SeverityNumber.ERROR,
        EventPhase.INSTANT: SeverityNumber.INFO,
    }
)
HOST_SEVERITIES: Final[Mapping[str, SeverityNumber]] = MappingProxyType(
    {
        "debug": SeverityNumber.DEBUG,
        "info": SeverityNumber.INFO,
        "warning": SeverityNumber.WARN,
        "warn": SeverityNumber.WARN,
        "error": SeverityNumber.ERROR,
        "exception": SeverityNumber.ERROR,
        "critical": SeverityNumber.FATAL,
    }
)


##### VIEW #####
class OtlpView(EventView, frozen=True, kw_only=True):
    """What a span needs of a frame: its place in the tree, its time, what it carried and what it cost."""

    run_id: str
    thread_id: str = ""
    id: str
    parent: str = ""
    kind: EventKind
    phase: EventPhase
    name: str = ""
    node: str = ""
    step: int | None = None
    visit: int | None = None
    part: Part | None = None
    call_id: str = ""
    at: datetime
    model: ModelRef | None = None
    usage: Usage | None = None
    error: Failure | None = None
    payload: dict[str, Any] = msgspec.field(default_factory=dict)
    attributes: dict[str, Any] = msgspec.field(default_factory=dict)


##### IDS #####
class RunIds(IdGenerator):
    """The SDK asks for ids when a span starts: the ones pinned just before, random when none is pinned."""

    __slots__ = ("_fallback", "span", "trace")

    def __init__(self) -> None:
        self._fallback = RandomIdGenerator()
        self.trace: int | None = None
        self.span: int | None = None

    def generate_trace_id(self) -> int:
        return self.trace or self._fallback.generate_trace_id()

    def generate_span_id(self) -> int:
        return self.span or self._fallback.generate_span_id()


##### DRIVER #####
class OtlpDriver:
    """Spans (and, with `logs`, log records) from frames, on private providers, exported to every target."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("otlp", Locality.REMOTE, Workload.IO_BOUND, Isolation.LOOP)
    view: ClassVar[type[EventView]] = OtlpView
    phases: ClassVar[frozenset[EventPhase]] = PHASES

    __slots__ = (
        "_contexts",
        "_ids",
        "_log_exporters",
        "_logger",
        "_logs",
        "_open",
        "_settings",
        "_span_exporters",
        "_tracer",
        "_traces",
    )

    def __init__(
        self,
        settings: OtlpSettings | None = None,
        span_exporters: Sequence[SpanExporter] = (),
        log_exporters: Sequence[LogRecordExporter] = (),
    ) -> None:
        self._settings = settings
        self._span_exporters = tuple(span_exporters)
        self._log_exporters = tuple(log_exporters)
        self._ids = RunIds()
        self._traces: TracerProvider | None = None
        self._logs: LoggerProvider | None = None
        self._tracer: Tracer | None = None
        self._logger: Logger | None = None
        self._open: dict[str, Span] = {}
        ### closed spans' contexts, kept until their run's root closes: an instant may hang from a span already ended.
        self._contexts: dict[str, dict[str, SpanContext]] = {}

    ##### PRIVATE #####

    @staticmethod
    def _common_ns(at: datetime) -> int:
        """A frame's time in the nanoseconds OpenTelemetry stamps."""
        return int(at.timestamp() * NS)

    @staticmethod
    def _common_flat(value: Any) -> Primitive:
        """A value as an attribute: primitives as they are, anything else as JSON — e-serde canonicalizes what a
        source carried (pydantic messages, dataclass commands, structs, dates), unknown objects as their text."""
        match value:
            case str() | bool() | int() | float():
                return value
            case _:
                return eserde.dumps(value, default=str).decode()

    @property
    def _common_settings(self) -> OtlpSettings:
        return self._settings or st.providers.drivers.sink.otlp

    def _common_headers(self, name: str) -> dict[str, str]:
        target = self._common_settings.targets[name]
        return {key: secret.get_secret_value() for key, secret in target.headers.items()}

    def _enter_traces(self, resource: Resource) -> TracerProvider:
        config = self._common_settings
        provider = TracerProvider(resource=resource, id_generator=self._ids)
        timeout, flush = config.timeout.total_seconds(), config.flush.total_seconds() * MS
        remote = [
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=f"{target.endpoint.rstrip('/')}/v1/traces",
                    headers=self._common_headers(name),
                    timeout=timeout,
                ),
                schedule_delay_millis=flush,
            )
            for name, target in config.targets.items()
        ]
        local = [SimpleSpanProcessor(exporter) for exporter in self._span_exporters]
        _ = [provider.add_span_processor(processor) for processor in (*remote, *local)]
        return provider

    def _enter_logs(self, resource: Resource) -> LoggerProvider:
        config = self._common_settings
        provider = LoggerProvider(resource=resource)
        timeout, flush = config.timeout.total_seconds(), config.flush.total_seconds() * MS
        remote = [
            BatchLogRecordProcessor(
                OTLPLogExporter(
                    endpoint=f"{target.endpoint.rstrip('/')}/v1/logs",
                    headers=self._common_headers(name),
                    timeout=timeout,
                ),
                schedule_delay_millis=flush,
            )
            for name, target in config.targets.items()
        ]
        local = [SimpleLogRecordProcessor(exporter) for exporter in self._log_exporters]
        _ = [provider.add_log_record_processor(processor) for processor in (*remote, *local)]
        return provider

    def _common_tracer(self) -> Tracer:
        match self._tracer:
            case None:
                msg = "OtlpDriver is not open: the lifespan opens it before the bus delivers"
                raise SinkError(msg)
            case tracer:
                return tracer

    @classmethod
    def _send_attributes(cls, view: OtlpView) -> dict[str, Primitive]:
        """The span's attributes in the three dialects, from what the frame carries."""
        model, usage = view.model or ModelRef(), view.usage
        named = {
            "etrack.run_id": view.run_id,
            "etrack.thread_id": view.thread_id,
            "etrack.kind": str(view.kind),
            "etrack.node": view.node,
            "etrack.call_id": view.call_id,
            "session.id": view.thread_id,
            "gen_ai.conversation.id": view.thread_id,
            "langfuse.session.id": view.thread_id,
            "gen_ai.operation.name": OPERATIONS.get(view.kind, ""),
            "openinference.span.kind": OPENINFERENCE.get(view.kind, "CHAIN"),
            "langfuse.observation.type": LANGFUSE.get(view.kind, "span"),
            "gen_ai.request.model": model.name if view.kind is EventKind.LLM else "",
            "gen_ai.provider.name": model.provider,
            "llm.model_name": model.name if view.kind is EventKind.LLM else "",
            "gen_ai.tool.name": view.name if view.kind in {EventKind.TOOL, EventKind.MCP} else "",
            "gen_ai.tool.call.id": view.call_id,
            "gen_ai.agent.name": view.name if view.kind in {EventKind.AGENT, EventKind.SUBAGENT} else "",
        }
        measured = {
            "etrack.step": view.step,
            "etrack.visit": view.visit,
            "gen_ai.usage.input_tokens": usage.input_tokens if usage else None,
            "gen_ai.usage.output_tokens": usage.output_tokens if usage else None,
            "llm.token_count.prompt": usage.input_tokens if usage else None,
            "llm.token_count.completion": usage.output_tokens if usage else None,
            "llm.token_count.total": usage.total_tokens if usage else None,
        }
        params = {f"gen_ai.request.{key}": cls._common_flat(value) for key, value in model.params.items()}
        extra = {key: cls._common_flat(value) for key, value in view.attributes.items()}
        return {
            **{key: value for key, value in named.items() if value},
            **{key: value for key, value in measured.items() if value is not None},
            **params,
            **extra,
        }

    def _send_parent(self, view: OtlpView) -> Any:
        """The context a new span hangs from: its parent open, its parent closed in this run, or a fresh trace."""
        known = self._contexts.get(view.run_id, {})
        match (self._open.get(view.parent), known.get(view.parent)):
            case (None, None):
                return None
            case (None, SpanContext() as closed):
                return trace.set_span_in_context(NonRecordingSpan(closed))
            case _:
                return trace.set_span_in_context(self._open[view.parent])

    def _send_start(self, view: OtlpView) -> Span:
        self._ids.trace, self._ids.span = w3c_trace(view.run_id), w3c_span(view.id)
        try:
            span = self._common_tracer().start_span(
                view.name or str(view.kind),
                context=self._send_parent(view),
                attributes=self._send_attributes(view),
                start_time=self._common_ns(view.at),
            )
        finally:
            self._ids.trace, self._ids.span = None, None
        _ = view.payload and span.set_attribute(
            "input.value", self._common_flat(view.payload.get("input", view.payload))
        )
        return span

    def _send_end(self, span: Span, view: OtlpView) -> None:
        span.set_attributes(self._send_attributes(view))
        _ = view.payload and span.set_attribute("output.value", self._common_flat(view.payload))
        match view.error:
            case None:
                span.set_status(Status(StatusCode.OK))
            case failure:
                span.set_status(Status(StatusCode.ERROR, f"{failure.type}: {failure.message}"))
                span.set_attributes({"exception.type": failure.type, "exception.message": failure.message})
        span.end(end_time=self._common_ns(view.at))
        self._contexts.setdefault(view.run_id, {})[view.id] = span.get_span_context()
        ### the root closed: nothing of this run will hang from a closed span any more.
        _ = view.parent == "" and self._contexts.pop(view.run_id, None)

    def _send_log(self, view: OtlpView) -> None:
        match self._logger:
            case None:
                pass
            case otel:
                otel.emit(
                    LogRecord(
                        timestamp=self._common_ns(view.at),
                        context=trace.set_span_in_context(
                            NonRecordingSpan(
                                SpanContext(
                                    w3c_trace(view.run_id),
                                    w3c_span(view.id),
                                    is_remote=False,
                                    trace_flags=TraceFlags(TraceFlags.SAMPLED),
                                )
                            )
                        ),
                        severity_number=SEVERITIES[view.phase],
                        severity_text=str(view.phase),
                        body=view.name or str(view.kind),
                        event_name=f"etrack.{view.kind}.{view.phase}",
                        attributes=self._send_attributes(view),
                    )
                )

    def _processor_emit(self, _logger: object, method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        match self._logger:
            case None:
                pass
            case otel:
                attributes = {
                    key: self._common_flat(value)
                    for key, value in event_dict.items()
                    if key != "event" and value is not None
                }
                otel.emit(
                    LogRecord(
                        severity_number=HOST_SEVERITIES.get(method, SeverityNumber.INFO),
                        severity_text=method,
                        body=str(event_dict.get("event", "")),
                        attributes=attributes,
                    )
                )
        return event_dict

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        config = self._common_settings
        resource = Resource.create({**config.attributes, "service.name": config.service})
        self._traces = self._enter_traces(resource)
        self._tracer = self._traces.get_tracer("etrack")
        self._logs = self._enter_logs(resource) if config.logs or self._log_exporters else None
        self._logger = self._logs.get_logger("etrack") if self._logs else None
        logger.info("otlp opened", targets=sorted(config.targets), traces=config.traces, logs=self._logs is not None)
        return self

    async def __aexit__(self, *exc: object) -> None:
        ### spans a run never closed are ended now, so a crash still reaches the collectors.
        _ = [span.end() for span in self._open.values()]
        self._open.clear()
        self._contexts.clear()
        traces, logs = self._traces, self._logs
        self._traces, self._logs, self._tracer, self._logger = None, None, None, None
        ### shutdown flushes the batches over the network: blocking I/O, so it leaves the loop.
        _ = traces and await asyncio.to_thread(traces.shutdown)
        _ = logs and await asyncio.to_thread(logs.shutdown)
        logger.info("otlp closed")

    async def health(self) -> bool:
        """Open, and every batch flushed within the export timeout."""
        timeout = int(self._common_settings.timeout.total_seconds() * MS)
        match self._traces:
            case None:
                return False
            case provider:
                return await asyncio.to_thread(provider.force_flush, timeout)

    async def send(self, view: EventView) -> None:
        """Open, close or stamp the frame's span; with logs on, the frame is also a log record on it."""
        frame = OtlpView.project(view)
        traced = self._common_settings.traces
        match (frame.phase, traced):
            case (_, False):
                pass
            case (EventPhase.START, True):
                self._open[frame.id] = self._send_start(frame)
            case (EventPhase.INSTANT, True):
                self._send_end(self._send_start(frame), frame)
            case (EventPhase.END | EventPhase.ERROR, True):
                opened = self._open.pop(frame.id, None)
                _ = opened and self._send_end(opened, frame)
            case _:
                pass
        self._send_log(frame)

    def processor(self) -> Any:
        """A structlog processor for the host's own chain: every host log line also leaves as an OTel log record."""
        return self._processor_emit

    async def flush(self) -> bool:
        """Export every buffered span and record now."""
        traces = await asyncio.to_thread(self._traces.force_flush) if self._traces else True
        logs = await asyncio.to_thread(self._logs.force_flush) if self._logs else True
        return bool(traces and logs)
