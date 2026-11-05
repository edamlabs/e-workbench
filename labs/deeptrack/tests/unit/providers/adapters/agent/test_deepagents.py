"""tests/unit/providers/adapters/agent/deepagents: a roster built as a deep agent — prompts, names resolved or refused."""

from typing import Any

import msgspec
import pytest

from infra.errors import AgentError
from ports.agent import AgentPort
from ports.harness import Roster, Tier
from providers.adapters.agent.deepagents import DeepagentsAdapter, Law
from tests.support.fake import script
from tests.unit.providers.adapters.agent.conftest import Audit, Kit


async def test_deepagents_meets_port() -> None:
    async with DeepagentsAdapter() as adapter:
        assert isinstance(adapter, AgentPort)
        assert await adapter.health()


async def test_deepagents_subagent_spec(roster: Roster, kit: Kit) -> None:
    (helper,) = DeepagentsAdapter().subagents(roster, "lead", **kit())
    assert (helper["name"], helper["description"]) == ("helper", "A subagent that reads and uses the shared skill.")
    assert [getattr(tool, "name", "") for tool in helper["tools"]] == ["lookup"]
    assert [type(each) for each in helper["middleware"]] == [Audit]


async def test_deepagents_prompt_context_instructions_skills(roster: Roster, kit: Kit) -> None:
    (helper,) = DeepagentsAdapter().subagents(roster, "lead", **kit())
    assert helper["system_prompt"] == (
        "Dominio de prueba: pólizas y siniestros.\n\nHelp the lead.\n\n## Skill · glosario\n\nUna póliza es un contrato."
    )


async def test_deepagents_models_by_tier(roster: Roster, kit: Kit) -> None:
    high, low = script(), script()
    (helper,) = DeepagentsAdapter().subagents(roster, "lead", **kit(models={Tier.HIGH: high, Tier.LOW: low}))
    assert helper["model"] is low


async def test_deepagents_middleware_fresh_per_agent(roster: Roster, kit: Kit) -> None:
    adapter = DeepagentsAdapter()
    first = adapter.subagents(roster, "lead", **kit())[0]["middleware"][0]
    second = adapter.subagents(roster, "lead", **kit())[0]["middleware"][0]
    assert first is not second


async def test_deepagents_builds_named_graph(roster: Roster, kit: Kit) -> None:
    graph = DeepagentsAdapter().build(roster, "lead", **kit())
    assert graph.name == "lead"


@pytest.mark.parametrize(
    ("law", "entry", "overrides"),
    [
        (Law.ENTRY, "ghost", {}),
        (Law.TOOL, "lead", {"tools": {}}),
        (Law.MIDDLEWARE, "lead", {"middleware": {}}),
        (Law.TIER, "lead", {"models": {Tier.HIGH: object()}}),
    ],
    ids=["entry", "tool", "middleware", "tier"],
)
async def test_deepagents_refuses(roster: Roster, kit: Kit, law: Law, entry: str, overrides: dict[str, Any]) -> None:
    with pytest.raises(AgentError) as refused:
        DeepagentsAdapter().build(roster, entry, **kit(**overrides))
    assert refused.value.law is law


async def test_deepagents_refuses_depth(roster: Roster, kit: Kit) -> None:
    helper = roster.agents["helper"]
    deeper = msgspec.structs.replace(helper, spec=msgspec.structs.replace(helper.spec, subagents=("lead",)))
    nested = msgspec.structs.replace(roster, agents={**roster.agents, "helper": deeper})
    with pytest.raises(AgentError) as refused:
        DeepagentsAdapter().build(nested, "lead", **kit())
    assert (refused.value.law, refused.value.agent) == (Law.DEPTH, "helper")
