"""lifespan/engines: the engines branch, built on the providers branch already mounted.

Both validations are built: the SHACL engine over the validation server, and the passing one the arm without ontology
uses. Which one an arm runs is the arms service's table. The engines keep references only: nothing to close."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from engines.shacl import PassShaclEngine, ShaclEngine
from engines.state import EnginesState
from infra.settings import settings as st
from infra.state import State


@asynccontextmanager
async def lifespan(state: State) -> AsyncGenerator[None]:
    """Mount `state.engines`."""
    validation = state.providers.ontology.validation
    state.engines = EnginesState(
        shacl=ShaclEngine(validation, base=st.ontology_texts, shapes=st.ontology_shapes), passing=PassShaclEngine()
    )
    yield
