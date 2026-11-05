"""lifespan/ontology: the ontology branch — the reference server, seeded, and the validation server, empty.

Its own lifespan because a diagnostic (`deeptrack tools`) opens just the two servers, without a model."""

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager

from infra.settings import settings as st
from providers.drivers.ontology.openontologies import OpenOntologiesDriver
from providers.state import OntologyState


@asynccontextmanager
async def lifespan() -> AsyncGenerator[OntologyState]:
    """Both servers open for the block, closed in reverse on exit."""
    async with AsyncExitStack() as stack:
        enter = stack.enter_async_context
        yield OntologyState(
            reference=await enter(OpenOntologiesDriver(st.onto_ref_url, st.LABS_ONTO_TOKEN, seed=st.ontology_texts)),
            validation=await enter(OpenOntologiesDriver(st.onto_val_url, st.LABS_ONTO_TOKEN)),
        )
