"""lifespan/sealed: the process tree — providers, engines, services, in that order, sealed; closed in reverse on exit.

From here a write raises and a typo names its siblings."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from infra.config.providers import SinkKind
from infra.lifespan import engines, providers, services
from infra.state import State
from ports.chat import ChatPort
from ports.classify import ClassifyPort


@asynccontextmanager
async def lifespan(
    chat: ChatPort | None = None,
    classify: ClassifyPort | None = None,
    *,
    sinks: frozenset[SinkKind] | None = None,
    forward: bool | None = None,
) -> AsyncGenerator[State]:
    """The whole tree open for the block; a caller may hand in the chat and classify providers, and the sinks."""
    state = State()
    async with (
        providers.lifespan(state, chat, classify, sinks=sinks, forward=forward),
        engines.lifespan(state),
        services.lifespan(state),
    ):
        state.seal()
        yield state
