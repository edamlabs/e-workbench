"""providers/drivers/ontology/openontologies: OpenOntologiesDriver — one Open Ontologies server over MCP Streamable HTTP.

The session stays open for the provider's whole life: the server's store is in memory, and a session per call would
see it empty. The server already advertises only its whitelist (`--tools-allow`); the driver exposes exactly what
it advertises. `seed` is loaded once on open — the reference ontology a read-only server serves."""

from collections.abc import Mapping
from contextlib import AsyncExitStack
from types import MappingProxyType
from typing import Any, ClassVar, Self

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, ToolException
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp.shared.exceptions import McpError

from infra.config.base import Secret
from infra.errors import OntologyError
from infra.logger import logger
from ports.provider import Isolation, Locality, ProviderSpec, Workload

### what the MCP stack raises for an unreachable server, a refused call or a tool that answered isError.
FOREIGN: tuple[type[BaseException], ...] = (OSError, httpx.HTTPError, McpError, ToolException)


class OpenOntologiesDriver:
    """A server's tools by name over one open session, and a call that answers the tool's text."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("openontologies", Locality.SIDECAR, Workload.IO_BOUND, Isolation.LOOP)

    __slots__ = ("_client", "_seed", "_stack", "_tools", "_url")

    def __init__(self, url: str, token: Secret | None = None, seed: tuple[str, ...] = ()) -> None:
        headers = {"Authorization": f"Bearer {token.get_secret_value()}"} if token else {}
        self._client = MultiServerMCPClient(
            {"server": {"transport": "streamable_http", "url": url, "headers": headers}}
        )
        self._url = url
        self._seed = seed
        self._stack = AsyncExitStack()
        self._tools: Mapping[str, BaseTool] = MappingProxyType({})

    @staticmethod
    def _call_text(result: Any) -> str:
        """A tool's result as its text: a bare string, or the text blocks of a content list."""
        match result:
            case str():
                return result
            case list():
                return "".join(str(block.get("text", "")) for block in result if isinstance(block, dict))
            case other:
                return str(other)

    async def _enter_session(self) -> Mapping[str, BaseTool]:
        try:
            session = await self._stack.enter_async_context(self._client.session("server"))
            return MappingProxyType({tool.name: tool for tool in await load_mcp_tools(session)})
        except* FOREIGN as group:
            msg = f"openontologies {self._url}: cannot open a session ({group.exceptions[0]})"
            raise OntologyError(msg) from group

    ############################################################

    async def __aenter__(self) -> Self:
        self._tools = await self._enter_session()
        [await self.call("onto_load", {"turtle": text}) for text in self._seed]
        logger.info(
            "ontology open", driver="openontologies", url=self._url, tools=sorted(self._tools), seeded=len(self._seed)
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._stack.aclose()
        self._tools = MappingProxyType({})
        logger.info("ontology closed", driver="openontologies", url=self._url)

    async def health(self) -> bool:
        """Whether the server answers `onto_stats`; never raises."""
        try:
            await self.call("onto_stats", {})
        except OntologyError:
            return False
        return True

    @property
    def tools(self) -> Mapping[str, BaseTool]:
        """Every tool the server advertises, bound to the open session."""
        return self._tools

    async def call(self, tool: str, args: Mapping[str, Any], config: RunnableConfig | None = None) -> str:
        """Call one advertised tool; its text result. A tool the server does not advertise is refused here."""
        match self._tools.get(tool):
            case None:
                msg = f"openontologies {self._url}: {tool!r} is not advertised ({sorted(self._tools)})"
                raise OntologyError(msg)
            case found:
                try:
                    return self._call_text(await found.ainvoke(dict(args), config))
                except FOREIGN as error:
                    msg = f"openontologies {self._url}: {tool} failed ({error})"
                    raise OntologyError(msg) from error
