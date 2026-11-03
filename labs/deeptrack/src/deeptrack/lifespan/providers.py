"""lifespan/providers: the providers branch — the only place that names a concretion, opened on the shared stack.

The chat model is the one choice: Vertex unless the caller hands a provider in (a scripted model in tests).
`ontology` opens just the two servers — what a diagnostic needs without a model."""

from contextlib import AsyncExitStack

from deeptrack.state import OntologyState, ProvidersState
from infra.settings import settings as st
from infra.state import State
from ports.chat import ChatPort
from providers.drivers.chat.vertex import VertexChatDriver
from providers.drivers.ontology.openontologies import OpenOntologiesDriver
from providers.drivers.trace.langfuse import LangfuseTraceDriver


async def ontology(stack: AsyncExitStack) -> OntologyState:
    """The reference server, seeded with the ontology, and the validation server, empty."""
    servers = st.providers.drivers.ontology.openontologies
    reference = OpenOntologiesDriver(servers.ref_url, servers.token, seed=st.ontology.texts)
    return OntologyState(
        reference=await stack.enter_async_context(reference),
        validation=await stack.enter_async_context(OpenOntologiesDriver(servers.val_url, servers.token)),
    )


async def providers(state: State, stack: AsyncExitStack, chat: ChatPort | None = None) -> None:
    """Open every provider in dependency order and mount `state.providers`."""
    state.providers = ProvidersState(
        trace=await stack.enter_async_context(LangfuseTraceDriver()),
        ontology=await ontology(stack),
        chat=await stack.enter_async_context(chat or VertexChatDriver()),
    )
