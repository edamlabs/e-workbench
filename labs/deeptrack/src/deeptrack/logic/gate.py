"""logic/gate: ShaclGate — the deterministic node every proposal crosses; the agent cannot skip what it cannot call.

No proposal: the turn ends. A proposal that conforms goes to the operator. One that does not returns to the agent
with the violations as a validation message, until the retry cap closes the turn with the last report."""

from typing import Final, Literal

import msgspec
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from deeptrack.logic.state import ChatState
from deeptrack.models.proposal import Proposal
from engines.shacl import ShaclEngine
from ports.ontology import ShaclReport

RETRIES: Final[int] = 3
### "__end__" is LangGraph's END, spelled as the literal the route type checks.
type GateRoute = Literal["approval", "agent", "__end__"]


class ShaclGate:
    """The graph node over the SHACL engine: the proposal as Turtle in, a route out."""

    __slots__ = ("_engine",)

    def __init__(self, engine: ShaclEngine) -> None:
        self._engine = engine

    @staticmethod
    def _run_verdict(report: ShaclReport, spent: int) -> Command[GateRoute]:
        errors = msgspec.to_builtins(report.violations)
        match (report.conforms, spent >= RETRIES):
            case (True, _):
                return Command[GateRoute](goto="approval", update={"errores": [], "intentos": 0})
            case (False, False):
                feedback = f"[validación] La propuesta no cumple las reglas del dominio:\n{report.text}"
                return Command[GateRoute](
                    goto="agent",
                    update={
                        "propuesta": None,
                        "errores": errors,
                        "intentos": spent,
                        "messages": [HumanMessage(feedback, name="validador")],
                    },
                )
            case _:
                closing = f"La propuesta no superó la validación tras {spent} intentos:\n{report.text}"
                return Command[GateRoute](
                    goto="__end__", update={"propuesta": None, "errores": errors, "messages": [AIMessage(closing)]}
                )

    ############################################################

    async def run(self, state: ChatState, config: RunnableConfig) -> Command[GateRoute]:
        """Judge the pending proposal, or end the turn when there is none."""
        match state.get("propuesta"):
            case None:
                return Command[GateRoute](goto="__end__")
            case raw:
                proposal = msgspec.convert(raw, Proposal, strict=False)
                report = await self._engine.validate(proposal.turtle, config)
                return self._run_verdict(report, state.get("intentos", 0) + 1)
