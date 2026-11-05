"""engines/state: the engines branch — `state.engines.shacl` ≡ `engines/shacl.py`, built on the providers branch."""

from dataclasses import dataclass

from ports.validation import ValidationPort


@dataclass(frozen=True, slots=True)
class EnginesState:
    """The validations over the providers: `shacl` judges against the ontology, `passing` judges nothing."""

    shacl: ValidationPort
    passing: ValidationPort
