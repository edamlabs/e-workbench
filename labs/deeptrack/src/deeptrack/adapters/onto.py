"""adapters.onto: OntoAdapter — two MCP sessions over Streamable HTTP, held open for the process's whole life.

`ref` is the reference ontology the agent reads; `val` the scratch copy the gate clears, reloads and judges, one
proposal at a time behind a lock. Each server already advertises only its own whitelist (`--tools-allow`); the
agent's tuple narrows `ref` again to the two read tools. Every call goes through LangChain tools with the caller's
config, so each MCP call is a span the projector and Langfuse both see."""

import asyncio
from contextlib import AsyncExitStack
from types import TracebackType
from typing import Any, Final, Self

import msgspec
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

from deeptrack.infra.config.onto import OntoConfig
from deeptrack.models.shacl import ShaclReport

AGENT_TOOLS: Final[tuple[str, ...]] = ("onto_query", "onto_stats")


class OntoAdapter:
    """The two servers as named tools: the agent's read-only pair, the gate's validation round."""

    __slots__ = ("_client", "_lock", "_ref", "_shapes", "_stack", "_texts", "_val")

    def __init__(self, config: OntoConfig) -> None:
        headers = {"Authorization": f"Bearer {config.token.get_secret_value()}"} if config.token else {}
        self._client = MultiServerMCPClient(
            {
                "ref": {"transport": "streamable_http", "url": config.ref_url, "headers": headers},
                "val": {"transport": "streamable_http", "url": config.val_url, "headers": headers},
            }
        )
        self._texts = tuple((config.directory / name).read_text() for name in config.files)
        self._shapes = (config.directory / config.shapes).read_text()
        self._stack = AsyncExitStack()
        self._lock = asyncio.Lock()
        self._ref: dict[str, BaseTool] = {}
        self._val: dict[str, BaseTool] = {}

    async def _enter_session(self, server: str) -> dict[str, BaseTool]:
        session = await self._stack.enter_async_context(self._client.session(server))
        return {tool.name: tool for tool in await load_mcp_tools(session)}

    async def _common_load(self, tools: dict[str, BaseTool], config: RunnableConfig | None = None) -> None:
        ### in order: the schema before the data that instantiates it.
        [await tools["onto_load"].ainvoke({"turtle": text}, config) for text in self._texts]

    @staticmethod
    def _common_text(result: Any) -> str:
        """An MCP tool's result as its text: a bare string, or the text blocks of a content list."""
        match result:
            case str():
                return result
            case list():
                return "".join(block.get("text", "") for block in result if isinstance(block, dict))
            case other:
                return str(other)

    ############################################################

    async def __aenter__(self) -> Self:
        self._ref = await self._enter_session("ref")
        self._val = await self._enter_session("val")
        await self._common_load(self._ref)
        return self

    async def __aexit__(
        self, kind: type[BaseException] | None, error: BaseException | None, trace: TracebackType | None
    ) -> None:
        await self._stack.aclose()

    @property
    def tools(self) -> tuple[BaseTool, ...]:
        """The ontologist's tools: SPARQL and stats over the reference, nothing that writes."""
        return tuple(self._ref[name] for name in AGENT_TOOLS)

    @property
    def names(self) -> frozenset[str]:
        """Every MCP tool name on both servers — how the projector tells an MCP span from a plain tool."""
        return frozenset(self._ref) | frozenset(self._val)

    @property
    def schemas(self) -> dict[str, dict[str, dict[str, Any]]]:
        """Each server's tools with their input schemas — the check that names and parameters are what we call."""
        return {
            server: {name: tool.args for name, tool in tools.items()}
            for server, tools in (("ref", self._ref), ("val", self._val))
        }

    async def query(self, sparql: str) -> str:
        """A SPARQL query over the reference ontology; its JSON result as text."""
        return self._common_text(await self._ref["onto_query"].ainvoke({"query": sparql}))

    async def validate(self, turtle: str, config: RunnableConfig) -> ShaclReport:
        """Clear the copy, reload the ontology and the proposal, judge it by the shapes — one round at a time."""
        async with self._lock:
            await self._val["onto_clear"].ainvoke({}, config)
            await self._common_load(self._val, config)
            await self._val["onto_load"].ainvoke({"turtle": turtle}, config)
            raw = await self._val["onto_shacl"].ainvoke({"shapes": self._shapes, "inline": True}, config)
        return msgspec.json.decode(self._common_text(raw), type=ShaclReport)
