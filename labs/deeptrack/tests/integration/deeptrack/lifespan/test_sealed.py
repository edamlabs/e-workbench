"""The sealed tree: every branch mounted, every provider meets its port, and the shape is closed."""

import pytest

from deeptrack.lifespan.sealed import lifespan
from deeptrack.state import EnginesState, ProvidersState, ServicesState
from ports.chat import ChatPort
from ports.ontology import OntologyPort
from ports.provider import Provider
from ports.trace import TracePort
from tests.support.fake import FakeClassifier, ScriptedChat

pytestmark = pytest.mark.integration


async def test_sealed_branches_typed_by_port() -> None:
    async with lifespan(classify=FakeClassifier(), chat=ScriptedChat()) as state:
        assert isinstance(state.providers, ProvidersState)
        assert isinstance(state.engines, EnginesState)
        assert isinstance(state.services, ServicesState)
        ports = ((state.providers.chat, ChatPort), (state.providers.trace, TracePort))
        assert all(isinstance(provider, port) and isinstance(provider, Provider) for provider, port in ports)
        assert isinstance(state.providers.ontology.reference, OntologyPort)
        assert state.providers.ontology.reference is not state.providers.ontology.validation


async def test_sealed_rejects_drift() -> None:
    async with lifespan(classify=FakeClassifier(), chat=ScriptedChat()) as state:
        with pytest.raises(AttributeError, match="providers"):
            _ = state.provider
        with pytest.raises(RuntimeError, match="Sealed"):
            state.extra = object()
