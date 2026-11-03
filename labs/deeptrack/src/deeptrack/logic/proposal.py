"""logic/proposal: ProposalMiddleware — the only door to `propuesta`, and the tools that walk through it.

Mounted on the transactions subagent alone: its state schema adds the key, its tools write it through a
`Command`, and deepagents carries the key back up to the orchestrator when the subagent returns. A proposal that
breaks the model's contract (an unsafe name, a bad date) is a `ToolException`: the model reads it and corrects, the
node never crashes."""

from datetime import date
from typing import Annotated, Any, NotRequired

import msgspec
from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, StructuredTool, ToolException
from langgraph.types import Command

from deeptrack.models.proposal import Denuncia, Endoso, Proposal


class ProposalState(AgentState):
    """The subagent's state, plus the proposal it may leave."""

    propuesta: NotRequired[dict[str, Any] | None]


class ProposalMiddleware(AgentMiddleware):
    """State schema and tools of the proposing role: it proposes, it never executes."""

    state_schema = ProposalState

    def __init__(self) -> None:
        super().__init__()
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
        self, poliza: str, cobertura: str, fecha_ocurrencia: date, tool_call_id: Annotated[str, InjectedToolCallId]
    ) -> Command:
        """Propone la denuncia de un siniestro: póliza, cobertura afectada (nombres locales) y fecha ISO."""
        raw = {"poliza": poliza, "cobertura": cobertura, "fecha_ocurrencia": fecha_ocurrencia}
        return self._common_command(self._common_convert(raw, Denuncia), tool_call_id)

    async def endoso(self, poliza: str, quita: str, tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
        """Propone un endoso que quita una cobertura (nombres locales) de una póliza."""
        return self._common_command(self._common_convert({"poliza": poliza, "quita": quita}, Endoso), tool_call_id)
