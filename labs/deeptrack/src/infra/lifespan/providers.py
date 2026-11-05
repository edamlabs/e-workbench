"""lifespan/providers: the providers branch — the only place that names a concretion, opened on one stack.

The chat model is the one choice, read from a frozen table keyed by `DEEPTRACK_CHAT_PROVIDER` (Gemini API by default);
a caller may hand a provider in instead (a scripted model in tests). The ontology and track branches are lifespans of
their own, entered here."""

from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from types import MappingProxyType
from typing import Final, cast

from etrack.providers.adapters.topology.langgraph import LanggraphTopologyAdapter

from infra.config.providers import ChatProvider, SinkKind
from infra.lifespan import ontology, track
from infra.settings import settings as st
from infra.state import State
from ports.chat import ChatPort
from ports.classify import ClassifyPort
from providers.adapters.agent.deepagents import DeepagentsAdapter
from providers.drivers.chat.gemini import ChatGeminiDriver
from providers.drivers.chat.vertex import VertexDriver
from providers.drivers.classify.gemini import ClassifyGeminiDriver
from providers.drivers.harness.files import FilesDriver
from providers.state import ProvidersState

CHATS: Final[Mapping[ChatProvider, Callable[[], ChatPort]]] = MappingProxyType(
    {
        ChatProvider.GEMINI: lambda: ChatGeminiDriver(
            ref=st.DEEPTRACK_GEMINI_REF,
            api_key=st.GEMINI_API_KEY,
            thinking=st.DEEPTRACK_GEMINI_THINKING_LEVEL,
            timeout=st.DEEPTRACK_GEMINI_TIMEOUT,
        ),
        ChatProvider.VERTEX: lambda: VertexDriver(
            ref=st.DEEPTRACK_VERTEX_REF,
            project=st.DEEPTRACK_VERTEX_PROJECT,
            location=st.DEEPTRACK_VERTEX_LOCATION,
            thinking=st.DEEPTRACK_VERTEX_THINKING_LEVEL,
            timeout=st.DEEPTRACK_VERTEX_TIMEOUT,
        ),
    }
)


@asynccontextmanager
async def lifespan(
    state: State,
    chat: ChatPort | None = None,
    classify: ClassifyPort | None = None,
    *,
    sinks: frozenset[SinkKind] | None = None,
    forward: bool | None = None,
) -> AsyncGenerator[None]:
    """Open every provider in dependency order, mount `state.providers`; close in reverse on exit."""
    async with AsyncExitStack() as stack:
        enter = stack.enter_async_context
        servers = await enter(ontology.lifespan())
        ### ty 0.0.96 refuses a `Self`-returning protocol as a context manager: the injectable chat crosses as one.
        model = cast("AbstractAsyncContextManager[ChatPort]", chat or CHATS[st.DEEPTRACK_CHAT_PROVIDER]())
        state.providers = ProvidersState(
            ontology=servers,
            chat=await enter(model),
            classify=await enter(
                classify
                or ClassifyGeminiDriver(
                    ref=st.DEEPTRACK_CLASSIFY_REF,
                    api_key=st.GEMINI_API_KEY,
                    thinking=st.DEEPTRACK_CLASSIFY_THINKING_LEVEL,
                    timeout=st.DEEPTRACK_CLASSIFY_TIMEOUT,
                )
            ),
            harness=await enter(FilesDriver(directory=st.DEEPTRACK_AGENTS_DIRECTORY)),
            agent=await enter(DeepagentsAdapter()),
            track=await enter(
                track.lifespan(
                    sinks=sinks or st.DEEPTRACK_TRACK_SINKS,
                    forward=st.DEEPTRACK_TRACK_FORWARD if forward is None else forward,
                    mcp=servers.names,
                )
            ),
            topology=await enter(LanggraphTopologyAdapter()),
        )
        yield
