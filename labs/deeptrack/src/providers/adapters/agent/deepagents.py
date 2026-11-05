"""providers/adapters/agent/deepagents: DeepagentsAdapter — a roster built as one deep agent and its subagents.

The entry agent becomes `create_deep_agent`; every agent it names in `subagents` becomes one of its subagents, flat, as
deepagents runs them (a subagent cannot hold subagents of its own). Each agent's prompt is the shared context, its
instructions and its skills preloaded, in that order — the stable part first, so a provider's prompt cache holds.
Every name the roster carries is resolved here and refused with an `AgentError` naming its law and agent when nothing
answers to it: ENTRY (the entry is an agent), DEPTH (a subagent names no subagents), TOOL, MIDDLEWARE, TIER."""

from collections.abc import Callable, Mapping
from enum import StrEnum, auto
from typing import Any, ClassVar, Self, cast

from deepagents import SubAgent, create_deep_agent
from deepagents.graph import DeepAgentState

from infra.errors import AgentError
from infra.logger import logger
from ports.harness import Agent, Roster, Tier
from ports.provider import Isolation, Locality, ProviderSpec, Workload


class Law(StrEnum):
    """The rules a roster must keep to be built."""

    ENTRY = auto()
    DEPTH = auto()
    TOOL = auto()
    MIDDLEWARE = auto()
    TIER = auto()


class DeepagentsAdapter:
    """Builds deep agents from rosters; holds nothing between builds."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("deepagents", Locality.EMBEDDED, Workload.CPU_BOUND, Isolation.LOOP)

    __slots__ = ()

    ##### PRIVATE #####

    @staticmethod
    def _build_pick[T](agent: Agent, law: Law, names: tuple[str, ...], known: Mapping[str, T]) -> list[T]:
        missing = sorted(set(names) - set(known))
        match missing:
            case []:
                return [known[name] for name in names]
            case _:
                raise AgentError(law, agent.spec.name, f"nothing answers to {missing}")

    @staticmethod
    def _build_model(agent: Agent, models: Mapping[Tier, Any]) -> Any:
        match models.get(agent.spec.tier):
            case None:
                raise AgentError(Law.TIER, agent.spec.name, f"no model serves the {agent.spec.tier} tier")
            case model:
                return model

    @staticmethod
    def _build_prompt(roster: Roster, agent: Agent) -> str:
        skills = [f"## Skill · {skill.name}\n\n{skill.body}" for skill in agent.skills]
        return "\n\n".join(part for part in (roster.context, agent.instructions, *skills) if part)

    def _build_subagent(
        self,
        roster: Roster,
        name: str,
        tools: Mapping[str, Any],
        middleware: Mapping[str, Callable[[], Any]],
        models: Mapping[Tier, Any],
    ) -> SubAgent:
        agent = roster.agents[name]
        _ = agent.spec.subagents and self._build_refuse(
            Law.DEPTH, name, f"a subagent cannot name subagents {list(agent.spec.subagents)}"
        )
        factories = self._build_pick(agent, Law.MIDDLEWARE, agent.spec.middleware, middleware)
        spec: SubAgent = {
            "name": name,
            "description": agent.spec.description,
            "system_prompt": self._build_prompt(roster, agent),
            "tools": self._build_pick(agent, Law.TOOL, agent.spec.tools, tools),
            "model": self._build_model(agent, models),
        }
        return {**spec, "middleware": [factory() for factory in factories]} if factories else spec

    @staticmethod
    def _build_entry(roster: Roster, entry: str) -> Agent:
        match roster.agents.get(entry):
            case None:
                raise AgentError(Law.ENTRY, entry, f"is no agent of the roster {sorted(roster.agents)}")
            case head:
                return head

    @staticmethod
    def _build_refuse(law: Law, agent: str, message: str) -> None:
        raise AgentError(law, agent, message)

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        logger.info("agent open", adapter="deepagents")
        return self

    async def __aexit__(self, *exc: object) -> None:
        logger.info("agent closed", adapter="deepagents")

    async def health(self) -> bool:
        """Always ready: the adapter holds no resource."""
        return True

    def subagents(
        self,
        roster: Roster,
        entry: str,
        *,
        tools: Mapping[str, Any],
        middleware: Mapping[str, Callable[[], Any]],
        models: Mapping[Tier, Any],
    ) -> list[SubAgent]:
        """The entry's subagents as deepagents specs, in the order the entry names them."""
        head = self._build_entry(roster, entry)
        return [self._build_subagent(roster, name, tools, middleware, models) for name in head.spec.subagents]

    def build(
        self,
        roster: Roster,
        entry: str,
        *,
        tools: Mapping[str, Any],
        middleware: Mapping[str, Callable[[], Any]],
        models: Mapping[Tier, Any],
        schema: type | None = None,
    ) -> Any:
        """The entry's compiled deep agent, its subagents built from the roster, every name resolved or refused."""
        head = self._build_entry(roster, entry)
        subagents = self.subagents(roster, entry, tools=tools, middleware=middleware, models=models)
        factories = self._build_pick(head, Law.MIDDLEWARE, head.spec.middleware, middleware)
        return create_deep_agent(
            model=self._build_model(head, models),
            tools=self._build_pick(head, Law.TOOL, head.spec.tools, tools),
            system_prompt=self._build_prompt(roster, head),
            middleware=[factory() for factory in factories],
            subagents=subagents,
            state_schema=cast("type[DeepAgentState] | None", schema),
            name=entry,
        )
