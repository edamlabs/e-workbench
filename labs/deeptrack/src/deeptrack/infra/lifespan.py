"""infra.lifespan: the composition root — sessions and clients opened in dependency order, closed in reverse."""

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.memory import InMemorySaver

from deeptrack.adapters.onto import OntoAdapter
from deeptrack.adapters.trace import TraceAdapter
from deeptrack.infra.settings import settings as st
from deeptrack.infra.state import RuntimeState
from deeptrack.instrument.chat import TracedChat
from deeptrack.instrument.projector import Sink
from deeptrack.logic.agent import InsuranceAgent
from deeptrack.logic.gate import ShaclGate
from deeptrack.logic.graph import ChatGraph


@asynccontextmanager
async def lifespan(sink: Sink, model: BaseChatModel | None = None) -> AsyncGenerator[RuntimeState]:
    """The runtime tree: ontology sessions, Langfuse, the model (Vertex unless one is handed in), the graph."""
    async with AsyncExitStack() as stack:
        onto = await stack.enter_async_context(OntoAdapter(st.onto))
        trace = await stack.enter_async_context(TraceAdapter(st.trace))
        chat_model = model or init_chat_model(st.model.ref, **st.model.kwargs)
        agent = InsuranceAgent(chat_model, onto).build()
        graph = ChatGraph(agent, ShaclGate(onto)).build(InMemorySaver())
        yield RuntimeState(onto=onto, trace=trace, chat=TracedChat(graph, trace, sink, onto.names))
