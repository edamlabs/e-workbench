"""Fixtures of the middleware tier: the proposing tools by name, how the agent calls one, and the validating variant."""

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.types import Command

from engines.shacl import ShaclEngine
from logic.middleware.proposal import ProposalMiddleware
from tests.support.fake import FakeOntology

type Tools = dict[str, BaseTool]
type Invoke = Callable[..., Awaitable[Command | ToolMessage]]
type Validated = Callable[..., Tools]


@pytest.fixture
def tools() -> Tools:
    """The proposing tools of the plain arm, by name."""
    return {tool.name: tool for tool in ProposalMiddleware().tools}


@pytest.fixture
def invoke() -> Invoke:
    """`await invoke(tool, **args)`: call a tool the way the agent does, as a tool call, so the call id is injected."""

    async def called(tool: BaseTool, **args: Any) -> Command | ToolMessage:
        return await tool.ainvoke({"type": "tool_call", "name": tool.name, "args": args, "id": "call-1"})

    return called


@pytest.fixture
def validated() -> Validated:
    """`validated(*verdicts)`: the proposing tools of the `prevalidate` arm over a fake server with scripted verdicts."""

    def built(*verdicts: bool) -> Tools:
        engine = ShaclEngine(FakeOntology(verdicts), base=(), shapes="shapes")
        return {tool.name: tool for tool in ProposalMiddleware(engine).tools}

    return built
