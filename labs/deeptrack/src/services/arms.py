"""services/arms: ArmsService — the chat service of each A/B arm, over the same providers and engines.

One variable per arm (`models/arm`): whether the ontologist stays in the roster, and which validation judges — the
gate's always, the proposing tools' only in `prevalidate`. The roster's names resolve here against this system: every
tool of the reference server plus `consultar_poliza`, the `proposal` middleware, and the one chat model behind every
tier. The agents' versions ride every run's metadata."""

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any, Final

from beartype import beartype
from etrack.logic.api import Tracker
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

from logic.gate import ShaclGate
from logic.graph import ChatGraph
from logic.guard import InputGuard
from logic.middleware.proposal import ProposalMiddleware
from logic.state import ChatState
from models.arm import Arm
from ports.agent import AgentPort
from ports.classify import ClassifyPort
from ports.harness import Roster, Tier
from ports.ontology import OntologyPort
from ports.validation import ValidationPort
from services.chat import ChatService
from tools.policy import PolicyTool

ENTRY: Final[str] = "insurance"
ONTOLOGIST: Final[str] = "ontologo"
### the arms whose roster keeps the ontologist.
ONTOLOGISTS: Final[frozenset[Arm]] = frozenset({Arm.FULL, Arm.PREVALIDATE})


@beartype
class ArmsService:
    """Builds the deep agent and the chat service of any arm; the providers and engines are shared by all."""

    __slots__ = (
        "_builder",
        "_classify",
        "_gates",
        "_model",
        "_reference",
        "_roster",
        "_traces",
        "_tracker",
        "_versions",
    )

    def __init__(
        self,
        *,
        builder: AgentPort,
        roster: Roster,
        model: BaseChatModel,
        reference: OntologyPort,
        classify: ClassifyPort,
        tracker: Tracker[RunnableConfig],
        shacl: ValidationPort,
        passing: ValidationPort,
        traces: str = "",
    ) -> None:
        self._builder = builder
        self._roster = roster
        self._model = model
        self._reference = reference
        self._classify = classify
        self._tracker = tracker
        self._traces = traces
        self._gates: Mapping[Arm, ValidationPort] = MappingProxyType(
            {Arm.FULL: shacl, Arm.PREVALIDATE: shacl, Arm.NO_ONTOLOGIST: shacl, Arm.NO_ONTOLOGY: passing}
        )
        self._versions = {name: agent.version for name, agent in roster.agents.items()}

    ############################################################

    def agent(self, arm: Arm = Arm.FULL) -> CompiledStateGraph:
        """The deep agent of the roster's entry for `arm`, every name it carries resolved against this system."""
        policy = PolicyTool(self._reference).tool
        tools: Mapping[str, Any] = {**self._reference.tools, policy.name: policy}
        validator = self._gates[arm] if arm is Arm.PREVALIDATE else None
        middleware: Mapping[str, Callable[[], Any]] = {"proposal": lambda: ProposalMiddleware(validator)}
        kept = self._roster if arm in ONTOLOGISTS else self._roster.without(ONTOLOGIST)
        return self._builder.build(
            kept, ENTRY, tools=tools, middleware=middleware, models=dict.fromkeys(Tier, self._model), schema=ChatState
        )

    def chat(self, arm: Arm) -> ChatService:
        """The chat service of `arm`: its agent behind the guard and the gate, tracked, its versions on every run."""
        gate = ShaclGate(self._gates[arm])
        graph = ChatGraph(self.agent(arm), gate, InputGuard(self._classify)).build(InMemorySaver())
        return ChatService(graph, self._tracker, traces=self._traces, versions=self._versions)
