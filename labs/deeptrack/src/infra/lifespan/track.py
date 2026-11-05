"""lifespan/track: etrack's branch — the configured sinks, the bus over them, the LangGraph source that feeds it.

The sinks open first and the bus after them, so the bus closes first and drains into sinks still open. The source
tells MCP calls by the tool names the ontology servers advertise."""

from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from types import MappingProxyType
from typing import Final

from etrack.infra.config.providers.drivers.sink.otlp import OtlpSettings, OtlpTarget
from etrack.ports.sink import WatchPort
from etrack.providers.adapters.bus.anyio import AnyioAdapter
from etrack.providers.adapters.sink.live import LiveAdapter
from etrack.providers.adapters.source.langgraph import LanggraphSourceAdapter
from etrack.providers.drivers.sink.otlp import OtlpDriver

from infra.config.providers import SinkKind
from infra.settings import settings as st
from providers.adapters.sink.console import ConsoleAdapter
from providers.state import TrackState

### typed by the concretions, not by `SinkPort`: ty 0.0.96 refuses a `Self`-returning protocol as a context manager.
LANGFUSE: Final[OtlpSettings] = OtlpSettings(
    targets={"langfuse": OtlpTarget(endpoint=st.langfuse_otlp, headers={"Authorization": st.langfuse_authorization})},
    service="deeptrack",
    attributes={
        "langfuse.environment": st.LABS_LANGFUSE_ENVIRONMENT,
        "deployment.environment.name": st.LABS_LANGFUSE_ENVIRONMENT,
    },
)
SINKS: Final[Mapping[SinkKind, Callable[[], LiveAdapter | ConsoleAdapter | OtlpDriver]]] = MappingProxyType(
    {SinkKind.LIVE: LiveAdapter, SinkKind.CONSOLE: ConsoleAdapter, SinkKind.OTLP: lambda: OtlpDriver(LANGFUSE)}
)


@asynccontextmanager
async def lifespan(*, sinks: frozenset[SinkKind], forward: bool, mcp: frozenset[str]) -> AsyncGenerator[TrackState]:
    """The branch open for the block; the live sink, when subscribed, is also what the viewer watches."""
    async with AsyncExitStack() as stack:
        enter = stack.enter_async_context
        opened = {kind: await enter(SINKS[kind]()) for kind in sorted(sinks)}
        bus = AnyioAdapter()
        _ = [bus.subscribe(sink) for sink in opened.values()]
        live = opened.get(SinkKind.LIVE)
        yield TrackState(
            bus=await enter(bus),
            sinks=opened,
            source=await enter(LanggraphSourceAdapter(mcp=mcp)),
            forward=forward,
            watch=live if isinstance(live, WatchPort) else None,
        )
