"""lifespan/engines: the engines branch, built on the providers branch already mounted — per arm."""

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Final

from deeptrack.models.arm import Arm
from deeptrack.state import EnginesState, ProvidersState
from engines.shacl import PassShaclEngine, ShaclEngine, ShaclValidation
from infra.settings import settings as st
from infra.state import State

### the one variable the `no_ontology` arm changes in this branch: the gate's engine judges nothing.
VALIDATIONS: Final[Mapping[Arm, Callable[[ProvidersState], ShaclValidation]]] = MappingProxyType(
    {
        Arm.FULL: lambda mounted: ShaclEngine(
            mounted.ontology.validation, base=st.ontology.texts, shapes=st.ontology.shapes_text
        ),
        Arm.NO_ONTOLOGIST: lambda mounted: ShaclEngine(
            mounted.ontology.validation, base=st.ontology.texts, shapes=st.ontology.shapes_text
        ),
        Arm.NO_ONTOLOGY: lambda _: PassShaclEngine(),
    }
)


def built(mounted: ProvidersState, arm: Arm) -> EnginesState:
    """The engines of one arm over the mounted providers."""
    return EnginesState(shacl=VALIDATIONS[arm](mounted))


async def engines(state: State) -> None:
    """Mount `state.engines` for the configured arm."""
    state.engines = built(state.providers, st.lab.arm)
