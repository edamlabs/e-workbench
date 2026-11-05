"""ports/ontology: an ontology server over MCP — its advertised tools, and a call by name; the SHACL report it answers.

`tools` are the server's tools as LangChain tools bound to the open session: whoever holds one calls the server, and
every call is a span. `call` is the same door for code that must not depend on a model choosing the tool."""

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

import msgspec
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from ports.provider import Provider


##### VALUES #####
class Violation(msgspec.Struct, frozen=True, kw_only=True):
    """One broken constraint: which, on which node, along which path, and the shape's own message."""

    constraint: str
    focus_node: str
    message: str = ""
    path: str = ""
    severity: str = ""


class ShaclReport(msgspec.Struct, frozen=True, kw_only=True):
    """The verdict over the whole store: conforms, and every violation when it does not."""

    conforms: bool
    violation_count: int = 0
    violations: tuple[Violation, ...] = ()

    @property
    def text(self) -> str:
        """The violations as lines a reader — a person or a model — takes in at once."""
        return "\n".join(f"- {each.message or each.constraint} ({each.focus_node})" for each in self.violations)


##### PORT #####
@runtime_checkable
class OntologyPort(Provider, Protocol):
    """The server's tools by name, and a call that returns the tool's text result."""

    @property
    def tools(self) -> Mapping[str, BaseTool]: ...

    async def call(self, tool: str, args: Mapping[str, Any], config: RunnableConfig | None = None) -> str: ...
