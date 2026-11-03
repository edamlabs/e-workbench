"""lifespan/sealed: the last lifespan — the tree is whole; from here a write raises and a typo names its siblings."""

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager

from deeptrack.lifespan.engines import engines
from deeptrack.lifespan.providers import providers
from deeptrack.lifespan.services import services
from infra.state import State
from ports.chat import ChatPort
from ports.classify import ClassifyPort


@asynccontextmanager
async def lifespan(chat: ChatPort | None = None, classify: ClassifyPort | None = None) -> AsyncGenerator[State]:
    """The process tree: providers, engines, services, in that order, sealed; closed in reverse on exit."""
    async with AsyncExitStack() as stack:
        state = State()
        await providers(state, stack, chat, classify)
        await engines(state)
        await services(state)
        state.seal()
        yield state
