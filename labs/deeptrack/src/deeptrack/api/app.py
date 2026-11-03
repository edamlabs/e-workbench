"""api/app: the ASGI app `make dev` serves (Granian) — the lifespan's tree mounted on startup, AG-UI and health routes.

The routes are plain functions registered here; the process tree is the same sealed `State` the CLI opens."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from litestar import Litestar, get

from deeptrack.api.agui import agui
from deeptrack.lifespan.sealed import lifespan


@asynccontextmanager
async def mounted(app: Litestar) -> AsyncGenerator[None]:
    """The process tree, open for the server's life, at `app.state.deeptrack`."""
    async with lifespan() as state:
        app.state.deeptrack = state
        yield


@get("/health")
async def health() -> dict[str, str]:
    """Liveness: the tree is mounted."""
    return {"status": "ok"}


app = Litestar(route_handlers=[agui, health], lifespan=[mounted])
