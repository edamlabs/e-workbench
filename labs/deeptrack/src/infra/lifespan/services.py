"""lifespan/services: the services branch — the arms over the providers and engines, the configured arm's chat, and
etrack's live canvas of its graph when a live sink watches.

The tracker is assembled here: frames on the bus, the LangGraph source of the providers branch, personal data masked.
Pure in-process objects: nothing to close."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from etrack.logic.api import Tracker
from etrack.logic.channel import EventChannel
from etrack.logic.viewer import Viewer
from etrack.models.event import LogView

from infra.settings import settings as st
from infra.state import State
from logic.graph import AGENT_STAGES
from ops.mask import mask_data
from services.arms import ArmsService
from services.state import ServicesState


@asynccontextmanager
async def lifespan(state: State) -> AsyncGenerator[None]:
    """Mount `state.services` for the configured arm."""
    providers, engines = state.providers, state.engines
    track = providers.track
    channel = EventChannel(track.bus, forward=LogView if track.forward else None)
    arms = ArmsService(
        builder=providers.agent,
        roster=providers.harness.roster,
        model=providers.chat.model,
        reference=providers.ontology.reference,
        classify=providers.classify,
        tracker=Tracker(channel, track.source, redact=lambda payload: mask_data(data=payload)),
        shacl=engines.shacl,
        passing=engines.passing,
        traces=st.langfuse_traces,
    )
    chat = arms.chat(st.DEEPTRACK_LAB_ARM)
    viewer = (
        Viewer(
            watch=track.watch,
            topology=providers.topology.read(chat.graph),
            labels={node: label for node, (label, _) in AGENT_STAGES.items()},
            kinds={node: kind for node, (_, kind) in AGENT_STAGES.items()},
        )
        if track.watch
        else None
    )
    state.services = ServicesState(chat=chat, arms=arms, viewer=viewer)
    yield
