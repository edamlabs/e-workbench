"""logic/guard: InputGuard — the node that classifies the user's message in parallel with the agent.

It starts from START beside the agent, so its latency hides behind the agent's first model call. `seguros` passes;
any other label raises `GuardError`, and LangGraph cancels the agent's task in the same step — the whole run stops,
nothing is committed. A classifier outage passes the message (logged): a basic filter must not take the product down."""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from deeptrack.logic.state import ChatState
from deeptrack.models.guard import GuardLabel
from infra.errors import GuardError, ModelError
from infra.logger import logger
from ports.classify import ClassifyPort

INSTRUCTION: Final[str] = (
    "Clasifica el mensaje de un usuario a un asistente de seguros. "
    "seguros: pólizas, coberturas, siniestros, endosos, asegurados, transacciones de seguros, y también saludos, "
    "agradecimientos o preguntas sobre qué puede hacer el asistente. "
    "fuera_de_tema: cualquier otra petición (programación, recetas, deportes, política, tareas generales). "
    "abuso: insultos, acoso o lenguaje ofensivo hacia el asistente o hacia terceros."
)
REPLIES: Final[Mapping[GuardLabel, str]] = MappingProxyType(
    {
        GuardLabel.FUERA_DE_TEMA: "Solo puedo ayudarte con pólizas, coberturas, siniestros y endosos.",
        GuardLabel.ABUSO: "No puedo continuar con este mensaje. Reformúlalo con respeto, por favor.",
    }
)


class InputGuard:
    """The graph node over a classifier port."""

    __slots__ = ("_classifier",)

    def __init__(self, classifier: ClassifyPort) -> None:
        self._classifier = classifier

    @staticmethod
    def _run_text(state: ChatState) -> str:
        """The message being guarded: the last one the user wrote."""
        said = [each for each in state.get("messages", []) if isinstance(each, HumanMessage) and not each.name]
        return said[-1].text if said else ""

    async def _run_label(self, text: str, config: RunnableConfig) -> GuardLabel:
        try:
            return GuardLabel(await self._classifier.classify(INSTRUCTION, text, tuple(GuardLabel), config))
        except ModelError as error:
            logger.warning("guard open on classifier failure", error=str(error))
            return GuardLabel.SEGUROS

    ############################################################

    async def run(self, state: ChatState, config: RunnableConfig) -> ChatState:
        """Pass the message (no update) or stop the run with the label and the user's reply."""
        match (text := self._run_text(state), await self._run_label(text, config) if text else GuardLabel.SEGUROS):
            case (_, GuardLabel.SEGUROS):
                return {"messages": []}
            case (_, label):
                raise GuardError(REPLIES[label], str(label))
