"""lifespan/providers: the providers branch — the only place that names a concretion, opened on the shared stack.

The chat model is the one choice, read from a frozen table keyed by `st.chat.provider` (Gemini API by default);
a caller may hand a provider in instead (a scripted model in tests).
`ontology` opens just the two servers — what a diagnostic needs without a model."""

from collections.abc import Callable, Mapping
from contextlib import AsyncExitStack
from types import MappingProxyType
from typing import Final

from deeptrack.state import OntologyState, ProvidersState
from infra.config.chat import ChatProvider
from infra.settings import settings as st
from infra.state import State
from ports.chat import ChatPort
from ports.classify import ClassifyPort
from ports.provider import Provider
from providers.drivers.chat.gemini import GeminiChatDriver
from providers.drivers.chat.vertex import VertexChatDriver
from providers.drivers.classify.gemini import GeminiClassifyDriver
from providers.drivers.ontology.openontologies import OpenOntologiesDriver
from providers.drivers.trace.langfuse import LangfuseTraceDriver

CHATS: Final[Mapping[ChatProvider, Callable[[], ChatPort]]] = MappingProxyType(
    {ChatProvider.GEMINI: GeminiChatDriver, ChatProvider.VERTEX: VertexChatDriver}
)


async def opened[P: Provider](stack: AsyncExitStack, provider: P) -> P:
    """A provider opened now and closed by the stack, in reverse order — typed by its port, not by its class."""
    entered = await provider.__aenter__()
    stack.push_async_exit(provider.__aexit__)
    return entered


async def ontology(stack: AsyncExitStack) -> OntologyState:
    """The reference server, seeded with the ontology, and the validation server, empty."""
    servers = st.providers.drivers.ontology.openontologies
    reference = OpenOntologiesDriver(servers.ref_url, servers.token, seed=st.ontology.texts)
    return OntologyState(
        reference=await opened(stack, reference),
        validation=await opened(stack, OpenOntologiesDriver(servers.val_url, servers.token)),
    )


async def providers(
    state: State, stack: AsyncExitStack, chat: ChatPort | None = None, classify: ClassifyPort | None = None
) -> None:
    """Open every provider in dependency order and mount `state.providers`."""
    state.providers = ProvidersState(
        trace=await opened(stack, LangfuseTraceDriver()),
        ontology=await ontology(stack),
        chat=await opened(stack, chat or CHATS[st.chat.provider]()),
        classify=await opened(stack, classify or GeminiClassifyDriver()),
    )
