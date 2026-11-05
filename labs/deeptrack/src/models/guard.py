"""models/guard: what the input guard can say about a message — an enumeration, never free text."""

from enum import StrEnum, auto


class GuardLabel(StrEnum):
    """`seguros` passes; `fuera_de_tema` and `abuso` stop the run."""

    SEGUROS = auto()
    FUERA_DE_TEMA = auto()
    ABUSO = auto()
