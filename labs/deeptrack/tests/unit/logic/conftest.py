"""Fixtures of the logic tier: the gate over scripted verdicts, a user's conversation, the proposal and the run config."""

from collections.abc import Callable
from typing import Any

import pytest
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from engines.shacl import ShaclEngine
from logic.gate import ShaclGate
from logic.state import ChatState
from tests.conftest import PROPOSAL
from tests.support.fake import FakeOntology

type Gate = Callable[..., ShaclGate]
type Said = Callable[..., ChatState]


@pytest.fixture
def denuncia() -> dict[str, Any]:
    """The claim proposal as the state carries it."""
    return {"type": "denuncia", **PROPOSAL}


@pytest.fixture
def config() -> RunnableConfig:
    """One thread, the recursion limit the lab runs with."""
    return {"configurable": {"thread_id": "t"}, "recursion_limit": 80}


@pytest.fixture
def gate() -> Gate:
    """`gate(*verdicts)`: the SHACL gate over a fake server answering the scripted verdicts."""
    return lambda *verdicts: ShaclGate(ShaclEngine(FakeOntology(verdicts), base=(), shapes="shapes"))


@pytest.fixture
def said() -> Said:
    """`said(*texts)`: a state whose messages are what the user said."""
    return lambda *texts: {"messages": [HumanMessage(text) for text in texts]}
