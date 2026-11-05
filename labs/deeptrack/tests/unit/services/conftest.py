"""Fixtures of the services tier: the roster's subagents as the arms service would resolve them."""

from collections.abc import Callable
from typing import Any

import pytest

from logic.middleware.proposal import ProposalMiddleware
from ports.harness import Tier
from providers.adapters.agent.deepagents import DeepagentsAdapter
from services.arms import ENTRY, ONTOLOGIST
from tests.support.agents import ROSTER
from tests.support.fake import ToolOntology, script
from tools.policy import PolicyTool

type Roles = Callable[[bool], dict[str, Any]]


@pytest.fixture
def server() -> ToolOntology:
    """A reference server advertising a loading tool and the two reading ones."""
    return ToolOntology(["onto_load", "onto_query", "onto_stats"])


@pytest.fixture
def roles(server: ToolOntology) -> Roles:
    """`roles(ontologist)`: each subagent the arms service's kit builds, by name — without the ontologist when False."""

    def built(ontologist: bool) -> dict[str, Any]:
        roster = ROSTER if ontologist else ROSTER.without(ONTOLOGIST)
        policy = PolicyTool(server).tool
        specs = DeepagentsAdapter().subagents(
            roster,
            ENTRY,
            tools={**server.tools, policy.name: policy},
            middleware={"proposal": ProposalMiddleware},
            models=dict.fromkeys(Tier, script()),
        )
        return {spec["name"]: spec for spec in specs}

    return built
