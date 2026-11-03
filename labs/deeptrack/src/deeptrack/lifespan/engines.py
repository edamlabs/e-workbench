"""lifespan/engines: the engines branch, built on the providers branch already mounted."""

from deeptrack.state import EnginesState, ProvidersState
from engines.shacl import ShaclEngine
from infra.settings import settings as st
from infra.state import State


async def engines(state: State) -> None:
    """Mount `state.engines`: the SHACL engine over the validation server, the ontology and its shapes."""
    mounted: ProvidersState = state.providers
    state.engines = EnginesState(
        shacl=ShaclEngine(mounted.ontology.validation, base=st.ontology.texts, shapes=st.ontology.shapes_text)
    )
