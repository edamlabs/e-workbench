"""providers/drivers/ontology/openontologies: OpenOntologiesDriver — one Open Ontologies server over MCP Streamable HTTP.

The session stays open for the provider's whole life: the server's store is in memory, and a session per call would
see it empty. The server already advertises only its whitelist (`--tools-allow`); the driver exposes exactly what
it advertises. `seed` is loaded on open — the reference ontology a read-only server serves.

Each session lives in its own owner task inside the driver's task group: the MCP client's anyio scopes must close in
the task that opened them, and a reconnection is asked for from whichever request noticed the loss. Reopening tells
the old owner to close and starts a new one.

Reconnection is the driver's: a restarted server forgets the session (`Session terminated`) and its store. The
driver reopens the session and reloads the seed, then replays the call only when replaying is safe — a read, or the
`onto_clear` that starts a validation round. A write or a verdict cut mid-round raises instead: replayed on a fresh,
empty store it would judge a half-loaded ontology and answer a wrong verdict, silently."""

import asyncio
from collections.abc import Mapping
from contextlib import AsyncExitStack
from types import MappingProxyType
from typing import Any, ClassVar, Final, Self

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
FOREIGN: Final[tuple[type[BaseException], ...]] = (OSError, httpx.HTTPError, McpError, ToolException)
### what the MCP client raises when the server no longer knows the session id — it restarted.
LOST: Final[str] = "Session terminated"
### the calls that mean the same on a fresh store: reads, and the clear a validation round starts with.
REPLAYABLE: Final[frozenset[str]] = frozenset({"onto_query", "onto_stats", "onto_clear"})


class OpenOntologiesDriver:
    """A server's tools by name over one open session, and a call that answers the tool's text."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("openontologies", Locality.SIDECAR, Workload.IO_BOUND, Isolation.LOOP)

    __slots__ = ("_client", "_close", "_generation", "_group", "_lock", "_seed", "_stack", "_tools", "_url")

    def __init__(self, url: str, token: Secret | None = None, seed: tuple[str, ...] = ()) -> None:
        headers = {"Authorization": f"Bearer {token.get_secret_value()}"} if token else {}
        self._client = MultiServerMCPClient(
            {"server": {"transport": "streamable_http", "url": url, "headers": headers}}
        )
        self._url = url
        self._seed = seed
        self._stack = AsyncExitStack()
        self._lock = asyncio.Lock()
        self._generation = 0
        self._group: asyncio.TaskGroup | None = None
        self._close = asyncio.Event()
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

    async def _call_invoke(self, tool: str, args: Mapping[str, Any], config: RunnableConfig | None) -> str:
        """One call on the current session; foreign errors pass through for `call` to read."""
        match self._tools.get(tool):
            case None:
                msg = f"openontologies {self._url}: {tool!r} is not advertised ({sorted(self._tools)})"
                raise OntologyError(msg)
            case found:
                return self._call_text(await found.ainvoke(dict(args), config))

    async def _call_reopen(self, lost: int) -> None:
        """A fresh session and a reloaded seed — once per lost session, however many calls noticed it."""
        async with self._lock:
            match self._generation == lost:
                case True:
                    self._close.set()
                    await self._common_open()
                    self._generation += 1
                    logger.warning(
                        "ontology reconnected", driver="openontologies", url=self._url, reseeded=len(self._seed)
                    )
                case False:
                    pass

    async def _call_replay(self, tool: str, args: Mapping[str, Any], config: RunnableConfig | None) -> str:
        """The one replay after a reopen: a second failure is the caller's, never another loop."""
        try:
            return await self._call_invoke(tool, args, config)
        except FOREIGN as error:
            msg = f"openontologies {self._url}: {tool} failed after reconnecting ({error})"
            raise OntologyError(msg) from error

    async def _common_own(self, ready: asyncio.Future[Mapping[str, BaseTool]], close: asyncio.Event) -> None:
        """The session's owner: open it, hand its tools over, hold it until told to close — then close it here."""
        try:
            async with self._client.session("server") as session:
                ready.set_result(MappingProxyType({tool.name: tool for tool in await load_mcp_tools(session)}))
                await close.wait()
        except* FOREIGN as group:
            failure = OntologyError(f"openontologies {self._url}: cannot open a session ({group.exceptions[0]})")
            ### before ready: the opener raises it; after: the session died with its server — the next call reopens.
            match ready.done():
                case False:
                    ready.set_exception(failure)
                case True:
                    logger.warning("ontology session ended", driver="openontologies", url=self._url, error=str(failure))

    async def _common_open(self) -> None:
        """A new owner task, its session's tools, the seed loaded."""
        match self._group:
            case None:
                msg = f"openontologies {self._url}: the driver is not open"
                raise OntologyError(msg)
            case group:
                ready: asyncio.Future[Mapping[str, BaseTool]] = asyncio.get_running_loop().create_future()
                self._close = asyncio.Event()
                group.create_task(self._common_own(ready, self._close))
                self._tools = await ready
        [await self._call_invoke("onto_load", {"turtle": text}, None) for text in self._seed]

    ############################################################

    async def __aenter__(self) -> Self:
        self._group = await self._stack.enter_async_context(asyncio.TaskGroup())
        await self._common_open()
        logger.info(
            "ontology open", driver="openontologies", url=self._url, tools=sorted(self._tools), seeded=len(self._seed)
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        ### the owner closes its session; the group then joins it, in the task that opened the group.
        self._close.set()
        await self._stack.aclose()
        self._group = None
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
        """Call one advertised tool; its text result. A lost session is reopened, the call replayed when safe."""
        generation = self._generation
        try:
            return await self._call_invoke(tool, args, config)
        except McpError as error:
            match (error.error.message == LOST, tool in REPLAYABLE):
                case (True, True):
                    await self._call_reopen(generation)
                    return await self._call_replay(tool, args, config)
                case (True, False):
                    await self._call_reopen(generation)
                    msg = f"openontologies {self._url}: the server restarted during {tool}; the session was reopened, the call not replayed"
                    raise OntologyError(msg) from error
                case _:
                    msg = f"openontologies {self._url}: {tool} failed ({error})"
                    raise OntologyError(msg) from error
        except FOREIGN as error:
            msg = f"openontologies {self._url}: {tool} failed ({error})"
            raise OntologyError(msg) from error
