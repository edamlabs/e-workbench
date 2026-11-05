"""logic/middleware/proposal: ProposalMiddleware — the only door to `propuesta`, and the tools that walk through it.

Mounted on the transactions subagent alone: its state schema adds the key, its tools write it through a
`Command`, and deepagents carries the key back up to the orchestrator when the subagent returns. A proposal that
breaks the model's contract (an unsafe name, a bad date) is a `ToolException`: the model reads it and corrects, the
node never crashes.

With a validator (the `prevalidate` arm) the ontology judges here, before the proposal lands: a violation is a
`ToolException` carrying the shapes' messages, read and acted on inside the agent's own loop. Without one, the gate
node judges after the agent — the position the A/B compares."""

from datetime import date
from typing import Annotated, Any, NotRequired

import msgspec
from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolCallId, StructuredTool, ToolException
from langgraph.types import Command

from models.proposal import Denuncia, Endoso, Proposal
from ports.validation import ValidationPort


class ProposalState(AgentState):
    """The subagent's state, plus the proposal it may leave."""

    propuesta: NotRequired[dict[str, Any] | None]


class ProposalMiddleware(AgentMiddleware):
    """State schema and tools of the proposing role: it proposes, it never executes."""

    state_schema = ProposalState

    def __init__(self, validator: ValidationPort | None = None) -> None:
        super().__init__()
        self._validator = validator
        self.tools = [
            StructuredTool.from_function(
                coroutine=self.denuncia,
                name="proponer_denuncia",
                description="Propone denunciar un siniestro sobre una póliza. Solo propone: no ejecuta nada.",
                handle_tool_error=True,
            ),
            StructuredTool.from_function(
                coroutine=self.endoso,
                name="proponer_endoso",
                description="Propone un endoso que quita una cobertura de una póliza. Solo propone: no ejecuta nada.",
                handle_tool_error=True,
            ),
        ]

    @staticmethod
    def _common_convert[P: (Denuncia, Endoso)](raw: dict[str, Any], kind: type[P]) -> P:
        """The model's arguments as a proposal, or the reason they are not one — in words the model can act on."""
        try:
            return msgspec.convert(raw, kind)
        except msgspec.ValidationError as error:
            msg = (
                f"Argumentos inválidos ({error}). Usa los nombres locales exactos que devuelve consultar_poliza "
                "(p. ej. pol-1001, cob-rc, cob-robo) y fechas ISO (AAAA-MM-DD)."
            )
            raise ToolException(msg) from error

    async def _common_admit(self, proposal: Proposal, config: RunnableConfig) -> Proposal:
        """The proposal, once the ontology admits it — or its violations, for the model to correct or explain."""
        match self._validator:
            case None:
                return proposal
            case validator:
                report = await validator.validate(proposal.turtle, config)
        match report.conforms:
            case True:
                return proposal
            case False:
                msg = f"La propuesta no cumple las reglas del dominio:\n{report.text}\nCorrígela o explica al usuario por qué no procede."
                raise ToolException(msg)

    @staticmethod
    def _common_command(proposal: Proposal, tool_call_id: str) -> Command:
        return Command(
            update={
                "propuesta": msgspec.to_builtins(proposal),
                "messages": [
                    ToolMessage(
                        f"Propuesta registrada para validación: {msgspec.json.encode(proposal).decode()}",
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    ############################################################

    async def denuncia(
        self,
        poliza: str,
        cobertura: str,
        fecha_ocurrencia: date,
        tool_call_id: Annotated[str, InjectedToolCallId],
        config: RunnableConfig,
    ) -> Command:
        """Propone la denuncia de un siniestro: póliza, cobertura afectada (nombres locales) y fecha ISO."""
        raw = {"poliza": poliza, "cobertura": cobertura, "fecha_ocurrencia": fecha_ocurrencia}
        admitted = await self._common_admit(self._common_convert(raw, Denuncia), config)
        return self._common_command(admitted, tool_call_id)

    async def endoso(
        self, poliza: str, quita: str, tool_call_id: Annotated[str, InjectedToolCallId], config: RunnableConfig
    ) -> Command:
        """Propone un endoso que quita una cobertura (nombres locales) de una póliza."""
        admitted = await self._common_admit(self._common_convert({"poliza": poliza, "quita": quita}, Endoso), config)
        return self._common_command(admitted, tool_call_id)
