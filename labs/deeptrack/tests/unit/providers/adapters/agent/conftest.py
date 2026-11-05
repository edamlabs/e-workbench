"""Fixtures of the agent adapter: the valid roster loaded, and the kit of tools, middleware and models it is built with."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import StructuredTool

from ports.harness import Roster, Tier
from providers.drivers.harness.files import FilesDriver
from tests.support.fake import script

type Kit = Callable[..., dict[str, Any]]


class Audit(AgentMiddleware):
    """A middleware that does nothing: one instance per agent that names it."""


@pytest.fixture
async def roster(valid: Path) -> Roster:
    """The valid roster, read by the files driver."""
    async with FilesDriver(directory=valid) as harness:
        return harness.roster


@pytest.fixture
def kit() -> Kit:
    """`kit(**overrides)`: the keyword arguments of `subagents` and `build`, with any of them replaced."""

    def built(**overrides: Any) -> dict[str, Any]:
        lookup = StructuredTool.from_function(func=lambda: "", name="lookup", description="lookup")
        return {
            "tools": {"lookup": lookup},
            "middleware": {"audit": Audit},
            "models": dict.fromkeys(Tier, script()),
            **overrides,
        }

    return built
