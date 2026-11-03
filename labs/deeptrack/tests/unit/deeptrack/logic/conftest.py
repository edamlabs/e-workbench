"""The outer graph over a scripted model and a fake validation server with scripted verdicts."""

from collections.abc import Callable

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

from deeptrack.logic.agent import InsuranceAgent
from deeptrack.logic.gate import ShaclGate
from deeptrack.logic.graph import ChatGraph
from engines.shacl import ShaclEngine
from tests.support.fake import FakeOntology, script

type Compile = Callable[..., CompiledStateGraph]


@pytest.fixture
def compiled() -> Compile:
    """Build the graph: `compiled(verdicts, *messages)`."""

    def build(verdicts: tuple[bool, ...], *messages: AIMessage) -> CompiledStateGraph:
        engine = ShaclEngine(FakeOntology(verdicts), base=(), shapes="shapes")
        agent = InsuranceAgent(script(*messages), FakeOntology()).build()
        return ChatGraph(agent, ShaclGate(engine)).build(InMemorySaver())

    return build
