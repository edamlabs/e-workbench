"""tests/support/agents: the system's real roster (agents/), loaded once, and the arms service over test doubles."""

import asyncio

from etrack.logic.api import Tracker
from etrack.logic.channel import EventChannel
from etrack.providers.adapters.bus.anyio import AnyioAdapter
from etrack.providers.adapters.source.langgraph import LanggraphSourceAdapter
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig

from engines.shacl import PassShaclEngine
from infra.config.providers import AGENTS
from ports.harness import Roster
from ports.ontology import OntologyPort
from ports.validation import ValidationPort
from providers.adapters.agent.deepagents import DeepagentsAdapter
from providers.drivers.harness.files import FilesDriver
from services.arms import ArmsService
from tests.support.fake import FakeClassifier


async def _load() -> Roster:
    async with FilesDriver(directory=AGENTS) as harness:
        return harness.roster


### the reading tools the reference server advertises (its server-side allowlist): what `ontologo` names.
READING: tuple[str, ...] = ("onto_query", "onto_stats")

### read at collection, before any test's loop: the agents directory is the contract every test builds on.
ROSTER: Roster = asyncio.run(_load())


def arms(
    model: BaseChatModel,
    reference: OntologyPort,
    *,
    shacl: ValidationPort | None = None,
    tracker: Tracker[RunnableConfig] | None = None,
) -> ArmsService:
    """The arms service the lifespan would build, over these doubles; the tracker, unless given, is never opened."""
    idle = Tracker(EventChannel(AnyioAdapter(), forward=None), LanggraphSourceAdapter())
    return ArmsService(
        builder=DeepagentsAdapter(),
        roster=ROSTER,
        model=model,
        reference=reference,
        classify=FakeClassifier(),
        tracker=tracker or idle,
        shacl=shacl or PassShaclEngine(),
        passing=PassShaclEngine(),
    )
