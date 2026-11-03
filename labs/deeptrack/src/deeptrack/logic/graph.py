"""logic/graph: ChatGraph — the outer graph: agent → gate → approval → execute.

The deep agent is one node; the gate is code; the approval is an `interrupt` the operator resumes with a
`Decision`; execution is a deterministic stub — no model ever reaches it. A rejection returns to the agent."""

import json
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Final, Literal

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer, Command, interrupt

from deeptrack.logic.gate import ShaclGate
from deeptrack.logic.state import ChatState
from deeptrack.models.proposal import Decision

type ApprovalRoute = Literal["execute", "agent"]


##### APPROVAL HANDLERS #####
def approve(_: ChatState) -> Command[ApprovalRoute]:
    """The operator approved: on to execution."""
    return Command[ApprovalRoute](goto="execute")


def reject(_: ChatState) -> Command[ApprovalRoute]:
    """The operator rejected: back to the agent, the proposal dropped."""
    note = HumanMessage("[operador] Propuesta rechazada. Informa al usuario.", name="operador")
    return Command[ApprovalRoute](goto="agent", update={"propuesta": None, "messages": [note]})


ROUTES: Final[Mapping[Decision, Callable[[ChatState], Command[ApprovalRoute]]]] = MappingProxyType(
    {Decision.APROBAR: approve, Decision.RECHAZAR: reject}
)


##### GRAPH #####
class ChatGraph:
    """The outer graph over the compiled deep agent and the gate."""

    __slots__ = ("_agent", "_gate")

    def __init__(self, agent: CompiledStateGraph, gate: ShaclGate) -> None:
        self._agent = agent
        self._gate = gate

    @staticmethod
    def _build_approval(state: ChatState) -> Command[ApprovalRoute]:
        decision = Decision(interrupt({"propuesta": state.get("propuesta")}))
        return ROUTES[decision](state)

    @staticmethod
    def _build_execute(state: ChatState) -> dict[str, object]:
        done = f"Transacción registrada (stub, sin core): {json.dumps(state.get('propuesta'), ensure_ascii=False)}"
        return {"propuesta": None, "messages": [AIMessage(done)]}

    ############################################################

    def build(self, checkpointer: Checkpointer) -> CompiledStateGraph:
        """The compiled outer graph; the checkpointer holds the proposal across the approval stop."""
        ### ty cannot prove a TypedDict subclass meets StateGraph's bound; LangGraph accepts it at runtime.
        graph = StateGraph(ChatState)  # ty: ignore[invalid-argument-type]
        graph.add_node("agent", self._agent)
        graph.add_node("gate", self._gate.run)
        graph.add_node("approval", self._build_approval)
        graph.add_node("execute", self._build_execute)
        graph.add_edge(START, "agent")
        graph.add_edge("agent", "gate")
        graph.add_edge("execute", END)
        return graph.compile(checkpointer=checkpointer, name="deeptrack")
