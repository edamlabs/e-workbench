"""models/arm: the arms of the ontology A/B — one variable each, same model, data, stack and graph topology."""

from enum import StrEnum, auto


class Arm(StrEnum):
    """`full`: ontologist + SHACL gate · `no_ontologist`: the gate alone · `no_ontology`: neither — the gate judges
    nothing, every proposal conforms. The policies' data store stays in every arm."""

    FULL = auto()
    NO_ONTOLOGIST = auto()
    NO_ONTOLOGY = auto()
