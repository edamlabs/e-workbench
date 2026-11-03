"""logic.ports: what the logic needs from the ontology servers, met by shape — the adapter never leaks in."""

from typing import Protocol

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from deeptrack.models.shacl import ShaclReport


class OntoPort(Protocol):
    """The reference ontology for the agent, a validation copy for the gate."""

    @property
    def tools(self) -> tuple[BaseTool, ...]:
        """The read-only MCP tools the ontologist subagent holds."""
        ...

    async def query(self, sparql: str) -> str:
        """A SPARQL query over the reference ontology, its JSON result as text."""
        ...

    async def validate(self, turtle: str, config: RunnableConfig) -> ShaclReport:
        """The proposal loaded over a fresh copy of the ontology and judged by the shapes."""
        ...
