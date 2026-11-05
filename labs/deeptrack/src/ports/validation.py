"""ports/validation: what the gate and the proposing tools need of a validation engine — a candidate in, a report out."""

from typing import Protocol, runtime_checkable

from langchain_core.runnables import RunnableConfig

from ports.ontology import ShaclReport


@runtime_checkable
class ValidationPort(Protocol):
    """A candidate graph (Turtle) judged against the shapes, under the caller's config."""

    async def validate(self, turtle: str, config: RunnableConfig | None = None) -> ShaclReport: ...
