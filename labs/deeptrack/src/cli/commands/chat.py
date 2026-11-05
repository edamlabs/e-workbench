"""cli/commands/chat: `deeptrack chat` — talk to the agents over the whole lifespan.

The whole tree opens first, so a missing service or credential fails at startup, not mid-turn. The terminal draws the
run tree itself (the console sink), so the frames are not also forwarded as log lines."""

from typing import Final

from rich.console import Console

from cli.session import ChatSession
from infra.config.providers import SinkKind
from infra.lifespan.sealed import lifespan
from services.state import ServicesState

SINKS: Final[frozenset[SinkKind]] = frozenset({SinkKind.CONSOLE, SinkKind.LIVE})


async def chat(thread: str = "default", message: str = "") -> None:
    """Talk to the agents; `--message` runs one turn and exits."""
    async with lifespan(sinks=SINKS, forward=False) as state:
        services: ServicesState = state.services
        await ChatSession(services.chat, thread, Console(highlight=False)).run(message)
