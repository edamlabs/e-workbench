"""lifespan/services: the services branch — the agent, the outer graph and the chat service, per arm."""

from langgraph.checkpoint.memory import InMemorySaver

from deeptrack.logic.agent import InsuranceAgent
from deeptrack.logic.gate import ShaclGate
from deeptrack.logic.graph import ChatGraph
from deeptrack.logic.guard import InputGuard
from deeptrack.models.arm import Arm
from deeptrack.services.chat import ChatService
from deeptrack.state import EnginesState, ProvidersState, ServicesState
from infra.settings import settings as st
from infra.state import State


def chat(mounted: ProvidersState, engines: EnginesState, arm: Arm) -> ChatService:
    """The chat service of one arm: the ontologist only in `full`, the guard in every arm."""
    agent = InsuranceAgent(mounted.chat.model, mounted.ontology.reference, ontologist=arm is Arm.FULL).build()
    graph = ChatGraph(agent, ShaclGate(engines.shacl), InputGuard(mounted.classify)).build(InMemorySaver())
    return ChatService(graph, mounted.trace, mounted.ontology.names)


async def services(state: State) -> None:
    """Mount `state.services` for the configured arm."""
    state.services = ServicesState(chat=chat(state.providers, state.engines, st.lab.arm))
