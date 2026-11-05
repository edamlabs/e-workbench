"""ports/harness: agents as data — what an agent is, independent of where it is kept and of the framework that runs it.

An agent is a spec (its frontmatter: name, description, tier, the tools, middleware, skills and subagents it names), its
instructions (the markdown body), the skills it preloads and a version (a digest of everything it is made of). A
roster is every agent of a system plus the context they share. A harness provider loads one and guarantees it is
whole; it knows nothing of models, tools or frameworks — those are resolved where the roster is built."""

from enum import StrEnum, auto
from typing import Protocol, Self, runtime_checkable

import msgspec

from ports.provider import Provider


##### VALUES #####
class Tier(StrEnum):
    """The model class an agent asks for; the composition root decides which model serves each."""

    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()


class AgentSpec(msgspec.Struct, frozen=True, kw_only=True, forbid_unknown_fields=True):
    """An agent's frontmatter: every field it may declare, nothing else."""

    name: str
    description: str
    tier: Tier = Tier.MEDIUM
    tools: tuple[str, ...] = ()
    middleware: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    subagents: tuple[str, ...] = ()


class Skill(msgspec.Struct, frozen=True, kw_only=True):
    """A shared skill: its name, what it is for, and the body an agent preloads."""

    name: str
    description: str
    body: str


class Agent(msgspec.Struct, frozen=True, kw_only=True):
    """One agent, whole: its spec, its instructions, the skills it preloads, and its version."""

    spec: AgentSpec
    instructions: str
    skills: tuple[Skill, ...] = ()
    version: str


class Roster(msgspec.Struct, frozen=True, kw_only=True):
    """Every agent of a system by name, and the context they all share."""

    agents: dict[str, Agent]
    context: str = ""

    def without(self, *names: str) -> Self:
        """The roster with these agents gone, and gone from every list of subagents that named them."""
        gone = frozenset(names)
        kept = {
            name: msgspec.structs.replace(
                agent,
                spec=msgspec.structs.replace(
                    agent.spec, subagents=tuple(each for each in agent.spec.subagents if each not in gone)
                ),
            )
            for name, agent in self.agents.items()
            if name not in gone
        }
        return msgspec.structs.replace(self, agents=kept)


##### PORT #####
@runtime_checkable
class HarnessPort(Provider, Protocol):
    """The system's agents, loaded and checked when the provider opens."""

    @property
    def roster(self) -> Roster: ...
