"""models/proposal: what the transactions subagent may propose — never execute — rendered as Turtle for the gate.

Identifiers are local names of the ontology's individuals (`pol-1001`), checked against a strict pattern on
decode: whatever the model writes, nothing but a safe local name ever reaches the Turtle the gate loads."""

from datetime import date
from enum import StrEnum, auto
from typing import Annotated, Final

import msgspec

PREFIXES: Final[str] = (
    "@prefix seg: <https://deeptrack.lab/seguros#> .\n@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
)
type LocalName = Annotated[str, msgspec.Meta(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]


class Denuncia(msgspec.Struct, frozen=True, kw_only=True, tag="denuncia"):
    """A claim report: the policy, the affected coverage, the day it happened."""

    poliza: LocalName
    cobertura: LocalName
    fecha_ocurrencia: date

    @property
    def turtle(self) -> str:
        """The claim as one new `seg:Siniestro`, open."""
        return (
            f"{PREFIXES}seg:propuesta a seg:Siniestro ; seg:poliza seg:{self.poliza} ; "
            f'seg:cobertura seg:{self.cobertura} ; seg:fechaOcurrencia "{self.fecha_ocurrencia}"^^xsd:date ; '
            "seg:abierto true ."
        )


class Endoso(msgspec.Struct, frozen=True, kw_only=True, tag="endoso"):
    """An endorsement that removes one coverage from a policy."""

    poliza: LocalName
    quita: LocalName

    @property
    def turtle(self) -> str:
        """The endorsement as one new `seg:Endoso`."""
        return f"{PREFIXES}seg:propuesta a seg:Endoso ; seg:endosa seg:{self.poliza} ; seg:quita seg:{self.quita} ."


type Proposal = Denuncia | Endoso


class Decision(StrEnum):
    """The operator's answer at the approval stop: the value a resume carries."""

    APROBAR = auto()
    RECHAZAR = auto()
