"""providers/drivers/ontology/openontologies: OpenOntologiesDriver — one Open Ontologies server over MCP Streamable HTTP.

The session stays open for the provider's whole life: the server's store is in memory, and a session per call would
see it empty. The server already advertises only its whitelist (`--tools-allow`); the driver exposes exactly what
it advertises. `seed` is loaded on open — the reference ontology a read-only server serves.

Each session lives in its own owner task inside the driver's task group: the MCP client's anyio scopes must close in
the task that opened them, and a reconnection is asked for from whichever request noticed the loss. The owner keeps
the session alive with an MCP ping every `HEARTBEAT` seconds — the server (rmcp) drops a session idle for 300 s.

The tools are the driver's own, stable across sessions: each forwards to whatever session is current. A restarted
server forgets the session (`Session terminated`) and its store; the driver reopens and reloads the seed, then replays
the call only when replaying is safe — a read, or the `onto_clear` that starts a validation round. A write or a verdict
cut mid-round fails instead: replayed on a fresh, empty store it would judge a half-loaded ontology. The agent's tools
turn a failure into a message the model reads; `call` raises it as an `OntologyError`."""

import asyncio
import functools
from collections.abc import Mapping
from contextlib import AsyncExitStack
from types import MappingProxyType
from typing import Any, ClassVar, Final, Self

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool, ToolException
from langchain_mcp_adapters.client import MultiServerMCPClient
from mcp import ClientSession
from mcp.shared.exceptions import McpError
from mcp.types import CallToolResult, Tool

from infra.config.base import Secret
from infra.errors import OntologyError
from infra.logger import logger
from ports.provider import Isolation, Locality, ProviderSpec, Workload

### what the MCP stack raises for an unreachable server, a refused call or a tool that answered isError.
FOREIGN: Final[tuple[type[BaseException], ...]] = (OSError, httpx.HTTPError, McpError, ToolException)
### what the MCP client raises when the server no longer knows the session id — it restarted, or dropped it idle.
LOST: Final[str] = "Session terminated"
### the calls that mean the same on a fresh store: reads, and the clear a validation round starts with.
REPLAYABLE: Final[frozenset[str]] = frozenset({"onto_query", "onto_stats", "onto_clear"})
### seconds between pings: under rmcp's 300 s keep-alive, with margin.
HEARTBEAT: Final[float] = 240.0


class OpenOntologiesDriver:
    """A server's tools by name, stable across sessions, and a call that answers the tool's text."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("openontologies", Locality.SIDECAR, Workload.IO_BOUND, Isolation.LOOP)

    __slots__ = (
        "_client",
        "_close",
        "_generation",
        "_group",
        "_internal",
        "_lock",
        "_seed",
        "_session",
        "_stack",
        "_tools",
        "_url",
    )

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
        self._session: ClientSession | None = None
        self._close = asyncio.Event()
        self._tools: Mapping[str, BaseTool] = MappingProxyType({})
        self._internal: Mapping[str, BaseTool] = MappingProxyType({})

    @staticmethod
    def _call_text(result: CallToolResult) -> str:
        """A tool result's text blocks, joined."""
        return "".join(getattr(block, "text", "") for block in result.content)

    async def _call_raw(self, tool: str, **args: Any) -> str:
        """One call on the current session, the reconnection decided here; a failure is a `ToolException`."""
        generation, session = self._generation, self._session
        try:
            result = await self._common_session(session).call_tool(tool, args)
        except McpError as error:
            return await self._call_lost(tool, args, generation, error)
        except (OSError, httpx.HTTPError) as error:
            msg = f"openontologies {self._url}: {tool} failed ({error})"
            raise ToolException(msg) from error
        match result.isError:
            case True:
                msg = f"openontologies {self._url}: {tool} answered an error ({self._call_text(result)})"
                raise ToolException(msg)
            case _:
                return self._call_text(result)

    async def _call_lost(self, tool: str, args: dict[str, Any], generation: int, error: McpError) -> str:
        """A session the server forgot: reopen it, replay once when safe, otherwise fail with what happened."""
        match (error.error.message == LOST, tool in REPLAYABLE):
            case (True, True):
                await self._call_reopen(generation)
                result = await self._common_session(self._session).call_tool(tool, args)
                return self._call_text(result)
            case (True, False):
                await self._call_reopen(generation)
                msg = f"openontologies {self._url}: the session was lost during {tool}; reopened, not replayed"
                raise ToolException(msg) from error
            case _:
                msg = f"openontologies {self._url}: {tool} failed ({error})"
                raise ToolException(msg) from error

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

    def _common_session(self, session: ClientSession | None) -> ClientSession:
        match session:
            case None:
                msg = f"openontologies {self._url}: the driver is not open"
                raise OntologyError(msg)
            case open_session:
                return open_session

    async def _common_beat(self, session: ClientSession, close: asyncio.Event, group: asyncio.TaskGroup) -> None:
        """One heartbeat: wait until closed or due; when due, ping and schedule the next — no loop, no growing stack."""
        try:
            await asyncio.wait_for(close.wait(), HEARTBEAT)
        except TimeoutError:
            try:
                await session.send_ping()
            except FOREIGN as error:
                ### the session is gone; the next call reopens it, a dead session needs no heartbeat.
                logger.warning("ontology heartbeat failed", driver="openontologies", url=self._url, error=str(error))
                return
            group.create_task(self._common_beat(session, close, group))

    async def _common_own(
        self, ready: asyncio.Future[ClientSession], close: asyncio.Event, group: asyncio.TaskGroup
    ) -> None:
        """The session's owner: open it, hand it over, keep it alive until told to close — then close it here."""
        try:
            async with self._client.session("server") as session:
                ready.set_result(session)
                group.create_task(self._common_beat(session, close, group))
                await close.wait()
        except* FOREIGN as failed:
            failure = OntologyError(f"openontologies {self._url}: cannot open a session ({failed.exceptions[0]})")
            ### before ready: the opener raises it; after: the session died with its server — the next call reopens.
            match ready.done():
                case False:
                    ready.set_exception(failure)
                case True:
                    logger.warning("ontology session ended", driver="openontologies", url=self._url, error=str(failure))

    def _common_tool(self, tool: Tool, *, handled: bool) -> BaseTool:
        """The driver's own tool for one advertised MCP tool: forwards to the current session, whatever it is."""
        return StructuredTool.from_function(
            coroutine=functools.partial(self._call_raw, tool.name),
            name=tool.name,
            description=tool.description or tool.name,
            args_schema=tool.inputSchema,
            handle_tool_error=handled,
        )

    async def _common_open(self) -> None:
        """A new owner task, its session, the tools bound once, the seed loaded."""
        match self._group:
            case None:
                msg = f"openontologies {self._url}: the driver is not open"
                raise OntologyError(msg)
            case group:
                ready: asyncio.Future[ClientSession] = asyncio.get_running_loop().create_future()
                self._close = asyncio.Event()
                group.create_task(self._common_own(ready, self._close, group))
                self._session = await ready
        advertised = (await self._session.list_tools()).tools
        ### the agent reads a failure as a message; `call` raises it. Both are bound once and outlive any session.
        self._tools = self._tools or MappingProxyType({t.name: self._common_tool(t, handled=True) for t in advertised})
        self._internal = self._internal or MappingProxyType(
            {t.name: self._common_tool(t, handled=False) for t in advertised}
        )
        [await self._call_raw("onto_load", turtle=text) for text in self._seed]

    ############################################################

    async def __aenter__(self) -> Self:
        self._group = await self._stack.enter_async_context(asyncio.TaskGroup())
        await self._common_open()
        logger.info(
            "ontology open", driver="openontologies", url=self._url, tools=sorted(self._tools), seeded=len(self._seed)
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        ### the owner closes its session and the heartbeat ends; the group then joins both, in the task that opened it.
        self._close.set()
        await self._stack.aclose()
        self._group = None
        self._session = None
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
        """Every tool the server advertises, for an agent: stable across sessions, failures read as messages."""
        return self._tools

    async def call(self, tool: str, args: Mapping[str, Any], config: RunnableConfig | None = None) -> str:
        """Call one advertised tool — a span under the caller's config; its text, or an `OntologyError`."""
        match self._internal.get(tool):
            case None:
                msg = f"openontologies {self._url}: {tool!r} is not advertised ({sorted(self._internal)})"
                raise OntologyError(msg)
            case found:
                try:
                    return str(await found.ainvoke(dict(args), config))
                except FOREIGN as error:
                    raise OntologyError(str(error)) from error
