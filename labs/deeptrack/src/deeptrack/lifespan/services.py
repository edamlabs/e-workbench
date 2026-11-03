"""lifespan/services: the services branch — the agent, the outer graph and the chat service over both branches below."""

from langgraph.checkpoint.memory import InMemorySaver

from deeptrack.logic.agent import InsuranceAgent
from deeptrack.logic.gate import ShaclGate
from deeptrack.logic.graph import ChatGraph
from deeptrack.services.chat import ChatService
from deeptrack.state import EnginesState, ProvidersState, ServicesState
from infra.state import State


async def services(state: State) -> None:
    """Mount `state.services`: the deep agent on the chat model and the reference, the gate on the SHACL engine."""
    mounted: ProvidersState = state.providers
    built: EnginesState = state.engines
    agent = InsuranceAgent(mounted.chat.model, mounted.ontology.reference).build()
    graph = ChatGraph(agent, ShaclGate(built.shacl)).build(InMemorySaver())
    state.services = ServicesState(chat=ChatService(graph, mounted.trace, mounted.ontology.names))
