"""Fixtures of the ontology driver tests: the lab's servers, the seeded query, and the container restart."""

import asyncio
from collections.abc import Awaitable, Callable

import pytest

from infra.settings import Settings
from infra.settings import settings as st

type Restart = Callable[[str], Awaitable[None]]


@pytest.fixture
def servers() -> Settings:
    """The settings of the lab's two ontology servers."""
    return st


@pytest.fixture
def ask() -> str:
    """A query true only once the seed is loaded."""
    return "ASK { <https://deeptrack.lab/seguros#pol-1001> ?p ?o }"


@pytest.fixture
def restart() -> Restart:
    """`await restart(container)`: restart one of the lab's containers and wait until its MCP endpoint answers again."""

    async def restarted(container: str) -> None:
        process = await asyncio.create_subprocess_exec(
            "docker", "restart", container, stdout=asyncio.subprocess.DEVNULL
        )
        await process.wait()
        await asyncio.sleep(2)

    return restarted
