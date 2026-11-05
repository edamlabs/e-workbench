"""logic/graph: ChatGraph — the outer graph: guard ∥ agent → gate → approval → execute.

The deep agent is one node; the gate is code; the approval is an `interrupt` the operator resumes with a
`Decision`; execution is a deterministic stub — no model ever reaches it. A rejection returns to the agent.

Every node says what a person reads and what it is (an `EventKind`): the outer graph's own nodes declare it with the
node; the deep agent's, which deepagents declares, are named here by id for the viewer."""

import json
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any, Final, Literal, cast, get_args

from beartype import beartype
from etrack.models.event import EventKind
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer, Command, interrupt

from logic.gate import GateRoute, ShaclGate
from logic.guard import InputGuard
from logic.state import ChatState
from models.proposal import Decision

type ApprovalRoute = Literal["execute", "agent"]


##### STAGES #####
STAGES: Final[Mapping[str, Mapping[str, str]]] = MappingProxyType(
    {
        "guard": {"label": "Guardia", "kind": EventKind.EVALUATION},
        "gate": {"label": "Validación", "kind": EventKind.EVALUATION},
        "approval": {"label": "Aprobación", "kind": EventKind.INTERRUPT},
        "execute": {"label": "Ejecución", "kind": EventKind.TOOL},
    }
)
AGENT_STAGES: Final[Mapping[str, tuple[str, EventKind]]] = MappingProxyType(
    {
        "agent:PatchToolCallsMiddleware.before_agent": ("Reparación", EventKind.NODE),
        "agent:model": ("Modelo", EventKind.LLM),
        "agent:tools": ("Herramientas", EventKind.TOOL),
        "agent:_ParentNotifierMiddleware.after_agent": ("Cierre", EventKind.NODE),
    }
)


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
@beartype
class ChatGraph:
    """The outer graph over the compiled deep agent and the gate."""

    __slots__ = ("_agent", "_gate", "_guard")

    def __init__(self, agent: CompiledStateGraph, gate: ShaclGate, guard: InputGuard) -> None:
        self._agent = agent
        self._gate = gate
        self._guard = guard

    @staticmethod
    def _build_decision(answer: object) -> Decision:
        """The operator's answer as a Decision: the bare value (CLI) or `{"decision": …}` (the UI's resolve payload)."""
        match answer:
            case {"decision": str() as said}:
                return Decision(said)
            case str():
                return Decision(answer)
            case other:
                msg = f"an approval is answered with a Decision, not {other!r}"
                raise ValueError(msg)

    @classmethod
    def _build_approval(cls, state: ChatState) -> Command[ApprovalRoute]:
        decision = cls._build_decision(interrupt({"propuesta": state.get("propuesta")}))
        return ROUTES[decision](state)

    @staticmethod
    def _build_execute(state: ChatState) -> ChatState:
        done = f"Transacción registrada (stub, sin core): {json.dumps(state.get('propuesta'), ensure_ascii=False)}"
        return {"propuesta": None, "messages": [AIMessage(done)]}

    ############################################################

    def build(self, checkpointer: Checkpointer) -> CompiledStateGraph:
        """The compiled outer graph; the checkpointer holds the proposal across the approval stop."""
        ### ty reads a TypedDict class's keys as instance attributes, so it misses LangGraph's TypedDict-like bound: the
        ### schema crosses as `Any` here, the one border where the upstream typing and the checker disagree.
        graph = StateGraph(cast("Any", ChatState))
        graph.add_node("guard", self._guard.run, metadata=dict(STAGES["guard"]))
        graph.add_node("agent", self._agent)
        ### a `Command` route is invisible to the drawing unless declared: the destinations are the route types' values.
        graph.add_node(
            "gate", self._gate.run, destinations=get_args(GateRoute.__value__), metadata=dict(STAGES["gate"])
        )
        graph.add_node(
            "approval",
            self._build_approval,
            destinations=get_args(ApprovalRoute.__value__),
            metadata=dict(STAGES["approval"]),
        )
        graph.add_node("execute", self._build_execute, metadata=dict(STAGES["execute"]))
        ### the guard runs beside the agent from START: a trip raises and cancels the agent in the same step.
        graph.add_edge(START, "guard")
        graph.add_edge("guard", END)
        graph.add_edge(START, "agent")
        graph.add_edge("agent", "gate")
        graph.add_edge("execute", END)
        return graph.compile(checkpointer=checkpointer, name="deeptrack")
