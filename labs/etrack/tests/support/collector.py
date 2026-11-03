"""tests/support/collector: a fake OTLP/HTTP collector — the real exporter posts to it, it decodes what it receives."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from werkzeug import Request, Response

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from google.protobuf.message import Message
    from opentelemetry.proto.trace.v1.trace_pb2 import Span
    from pytest_httpserver import HTTPServer

TRACES = "/v1/traces"
LOGS = "/v1/logs"


@dataclass(slots=True)
class FakeCollector:
    """Every OTLP request the server took: path, headers and the decoded body."""

    server: HTTPServer
    traces: list[ExportTraceServiceRequest]
    logs: list[ExportLogsServiceRequest]
    headers: list[dict[str, str]]

    @property
    def endpoint(self) -> str:
        return self.server.url_for("/").rstrip("/")

    def spans(self) -> Iterator[Span]:
        return (
            span
            for request in self.traces
            for resource in request.resource_spans
            for scope in resource.scope_spans
            for span in scope.spans
        )


def fake_collector(server: HTTPServer) -> FakeCollector:
    """Mount OTLP's two routes on the server, keeping every request decoded."""
    collector = FakeCollector(server=server, traces=[], logs=[], headers=[])

    def take(kind: type[Message], into: list) -> Callable[[Request], Response]:
        def handler(request: Request) -> Response:
            collector.headers.append(dict(request.headers))
            into.append(kind.FromString(request.get_data()))
            return Response(status=200, content_type="application/x-protobuf")

        return handler

    server.expect_request(TRACES, method="POST").respond_with_handler(take(ExportTraceServiceRequest, collector.traces))
    server.expect_request(LOGS, method="POST").respond_with_handler(take(ExportLogsServiceRequest, collector.logs))
    return collector
