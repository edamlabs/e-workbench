"""The outer graph over a scripted model and a fake validation server with scripted verdicts."""

from collections.abc import Callable

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

from engines.shacl import ShaclEngine
from logic.gate import ShaclGate
from logic.graph import ChatGraph
from logic.guard import InputGuard
from tests.support.agents import READING, arms
from tests.support.fake import FakeClassifier, FakeOntology, ToolOntology, script

type Compile = Callable[..., CompiledStateGraph]


@pytest.fixture
def compiled() -> Compile:
    """Build the graph: `compiled(verdicts, *messages, guard=FakeClassifier())` — the guard passes by default."""

    def build(
        verdicts: tuple[bool, ...], *messages: AIMessage, guard: FakeClassifier | None = None
    ) -> CompiledStateGraph:
        engine = ShaclEngine(FakeOntology(verdicts), base=(), shapes="shapes")
        agent = arms(script(*messages), ToolOntology(READING)).agent()
        return ChatGraph(agent, ShaclGate(engine), InputGuard(guard or FakeClassifier())).build(InMemorySaver())

    return build
