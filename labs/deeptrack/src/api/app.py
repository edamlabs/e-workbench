"""api/app: the ASGI app `make dev` serves (Granian) — the lifespan's tree mounted on startup, AG-UI, etrack's live canvas and health.

The routes are plain functions registered here; the process tree is the same sealed `State` the CLI opens."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from litestar import Litestar, get

from api.agui import agui
from api.viewer import viewer
from infra.lifespan.sealed import lifespan
from infra.logger import ELogger
from infra.settings import settings as st


@asynccontextmanager
async def mounted(app: Litestar) -> AsyncGenerator[None]:
    """The process tree, open for the server's life, at `app.state.deeptrack`."""
    ELogger.setup(env=st.APP_ENV)
    async with lifespan() as state:
        app.state.deeptrack = state
        yield


@get("/health")
async def health() -> dict[str, str]:
    """Liveness: the tree is mounted."""
    return {"status": "ok"}


app = Litestar(route_handlers=[agui, viewer, health], lifespan=[mounted])
