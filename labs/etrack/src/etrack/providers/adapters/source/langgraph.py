"""providers/adapters/source/langgraph: LanggraphSourceAdapter — a LangGraph run's callbacks reported as span edges.

LangChain reports every runnable it starts with its run id and its parent's; this source reads them inline, on the
caller's thread, and tells a fold what each one is: the root (`RUN`), a graph node (a chain named after its own
`langgraph_node`), a model call (`LLM`), a retriever, a tool — `SUBAGENT` when it is the tool a deep agent delegates
through (`task`), `MCP` when its name is one the host declares — and folds everything else (sequences, middleware
plumbing) away. Streamed pieces are read from LangChain's v1 content blocks, so text, reasoning and tool-call chunks
arrive typed whatever the provider. An interrupt bubbles up as `GraphInterrupt`: the span it crosses ends cleanly
and one `INTERRUPT` frame carries what is asked, once, under the span that raised it. `bind` pins the run's id as the
root run id, so LangChain, LangSmith and the frames name the run alike."""

import itertools
import uuid
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar, Final, Self

from langchain_core.callbacks import BaseCallbackHandler, BaseCallbackManager
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphBubbleUp, GraphInterrupt

from etrack.infra.errors import SourceError
from etrack.infra.logger import logger
from etrack.models.event import EventKind, Failure, ModelRef, Part, Usage
from etrack.ports.provider import Isolation, Locality, ProviderSpec, Workload
from etrack.ports.source import Edge

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from uuid import UUID

    from langchain_core.outputs import ChatGenerationChunk, GenerationChunk, LLMResult

    from etrack.models.event import RunScope
    from etrack.ports.source import FoldPort

### deepagents launches every subagent through one tool; its `subagent_type` argument names the subagent.
SUBAGENTS: Final[frozenset[str]] = frozenset({"task"})
PARTS: Final[Mapping[str, Part]] = MappingProxyType(
    {
        "text": Part.TEXT,
        "reasoning": Part.REASONING,
        "tool_call_chunk": Part.TOOL_CALL,
        "tool_call": Part.TOOL_CALL,
        "image": Part.IMAGE,
        "audio": Part.AUDIO,
        "video": Part.VIDEO,
        "file": Part.FILE,
    }
)
### the field each block type keeps its streamed piece in; text and reasoning pieces that are empty carry nothing.
PIECES: Final[Mapping[str, str]] = MappingProxyType(
    {"text": "text", "reasoning": "reasoning", "tool_call_chunk": "args", "tool_call": "args"}
)
WORDS: Final[frozenset[str]] = frozenset({"text", "reasoning"})
PARAMS: Final[tuple[str, ...]] = ("ls_temperature", "ls_max_tokens", "ls_model_type")


class LanggraphHandler(BaseCallbackHandler):
    """One run's callbacks, inline: each runnable classified and reported to the fold the moment LangChain announces it."""

    run_inline = True

    def __init__(self, fold: FoldPort, mcp: frozenset[str], subagents: frozenset[str]) -> None:
        super().__init__()
        self._fold = fold
        self._mcp = mcp
        self._subagents = subagents
        self._names: dict[str, str] = {}
        self._interrupted: set[int] = set()

    ##### PRIVATE #####

    @staticmethod
    def _common_hex(run: UUID | None) -> str:
        """A LangChain run id as the 32-hex id every frame uses; no run, no id."""
        return run.hex if run else ""

    @staticmethod
    def _common_name(serialized: dict[str, Any] | None, kwargs: dict[str, Any], fallback: str) -> str:
        """A runnable's name: the one LangChain passes, the serialized one, the last segment of its class path."""
        known = serialized or {}
        return str(kwargs.get("name") or known.get("name") or (known.get("id") or [fallback])[-1])

    @staticmethod
    def _common_meta(metadata: dict[str, Any] | None) -> tuple[str, str, int | None]:
        meta = metadata or {}
        step = meta.get("langgraph_step")
        return (
            str(meta.get("langgraph_node", "")),
            str(meta.get("checkpoint_ns", "")),
            step if isinstance(step, int) else None,
        )

    def _common_open(
        self,
        run: UUID,
        parent: UUID | None,
        kind: EventKind | None,
        name: str,
        metadata: dict[str, Any] | None,
        **fields: Any,
    ) -> None:
        node, ns, step = self._common_meta(metadata)
        self._names[self._common_hex(run)] = name
        self._fold.open(
            Edge(
                id=self._common_hex(run),
                parent=self._common_hex(parent),
                kind=kind,
                name=name,
                node=node,
                ns=ns,
                step=step,
                **fields,
            )
        )

    def _common_failure(self, run: UUID, error: BaseException) -> None:
        span = self._common_hex(run)
        match error:
            case GraphInterrupt():
                self._fold.close(span, {"interrupted": True})
                self._chain_interrupt(span, error)
            case GraphBubbleUp():
                self._fold.close(span, {"bubbled": type(error).__name__})
            case _:
                self._fold.close(span, {}, error=Failure(type=type(error).__name__, message=str(error)))

    def _chain_interrupt(self, span: str, error: GraphInterrupt) -> None:
        ### every ancestor sees the same exception: the first close is the innermost span, the one frame is emitted there.
        match id(error) in self._interrupted:
            case True:
                pass
            case _:
                self._interrupted.add(id(error))
                stops: Sequence[Any] = error.args[0] if error.args else ()
                values = [getattr(stop, "value", stop) for stop in stops]
                ids = [str(getattr(stop, "id", "")) for stop in stops]
                edge = Edge(
                    id=f"{span}:interrupt",
                    parent=span,
                    kind=EventKind.INTERRUPT,
                    name="interrupt",
                    payload={"value": values},
                    attributes={"etrack.interrupt.ids": ids},
                )
                self._fold.instant(edge)

    @staticmethod
    def _llm_blocks(message: Any) -> list[dict[str, Any]]:
        return list(getattr(message, "content_blocks", None) or [])

    @staticmethod
    def _llm_join(blocks: list[dict[str, Any]], kind: str) -> str:
        return "".join(str(block.get(kind, "")) for block in blocks if block.get("type") == kind)

    @staticmethod
    def _llm_usage(message: Any) -> Usage | None:
        match getattr(message, "usage_metadata", None):
            case None:
                return None
            case usage:
                inputs, outputs = usage.get("input_token_details", {}), usage.get("output_token_details", {})
                return Usage(
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                    reasoning_tokens=outputs.get("reasoning", 0),
                    cache_read_tokens=inputs.get("cache_read", 0),
                    cache_write_tokens=inputs.get("cache_creation", 0),
                )

    @staticmethod
    def _llm_model(metadata: dict[str, Any] | None, fallback: str) -> ModelRef:
        meta = metadata or {}
        params = {key.removeprefix("ls_"): meta[key] for key in PARAMS if key in meta}
        return ModelRef(
            provider=str(meta.get("ls_provider", "")), name=str(meta.get("ls_model_name") or fallback), params=params
        )

    @staticmethod
    def _llm_token(token: str | list[str | dict[str, Any]]) -> list[dict[str, Any]]:
        """A bare token as content blocks: a string is text, a list is its parts — strings as text, dicts as blocks."""
        parts = [token] if isinstance(token, str) else token
        return [{"type": "text", "text": part} if isinstance(part, str) else part for part in parts]

    @staticmethod
    def _llm_piece(block: dict[str, Any]) -> tuple[Part, dict[str, Any], str] | None:
        """A content block as a typed piece: text, reasoning and tool calls by their delta, media whole; empty words: none."""
        kind = str(block.get("type", ""))
        part = PARTS.get(kind, Part.CUSTOM)
        field = PIECES.get(kind, "")
        match (field, kind in WORDS):
            case ("", _):
                return part, {"block": block}, ""
            case (_, True) if not block.get(field):
                return None
            case _:
                named = {"name": block["name"]} if block.get("name") else {}
                return part, {"delta": block.get(field, ""), **named}, str(block.get("id") or "")

    def _llm_open(
        self, run: UUID, parent: UUID | None, metadata: dict[str, Any] | None, name: str, inputs: Any
    ) -> None:
        model = self._llm_model(metadata, name)
        self._common_open(run, parent, EventKind.LLM, model.name, metadata, model=model, payload={"input": inputs})

    ############################################################

    ##### CHAINS #####

    def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: dict[str, Any] | Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        name = str(kwargs.get("name") or (serialized or {}).get("name", ""))
        ### a compiled subgraph mounted as a node opens a second chain under the node, named like it: one span, not two.
        nested = self._names.get(self._common_hex(parent_run_id)) == name
        is_node = (metadata or {}).get("langgraph_node") == name and not nested
        match (parent_run_id, is_node):
            case (None, _):
                self._common_open(run_id, None, EventKind.RUN, name, metadata, payload={"input": inputs})
            case (_, True):
                self._common_open(run_id, parent_run_id, EventKind.NODE, name, metadata)
            case _:
                self._common_open(run_id, parent_run_id, None, name, metadata)

    def on_chain_end(self, outputs: dict[str, Any] | Any, *, run_id: UUID, **kwargs: Any) -> None:
        keys = sorted(outputs) if isinstance(outputs, dict) else []
        self._fold.close(self._common_hex(run_id), {"keys": keys})

    def on_chain_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._common_failure(run_id, error)

    ##### MODELS #####

    def on_chat_model_start(
        self,
        serialized: dict[str, Any] | None,
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        inputs = [{"role": message.type, "content": message.content} for batch in messages for message in batch]
        self._llm_open(run_id, parent_run_id, metadata, self._common_name(serialized, kwargs, "model"), inputs)

    def on_llm_start(
        self,
        serialized: dict[str, Any] | None,
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._llm_open(run_id, parent_run_id, metadata, self._common_name(serialized, kwargs, "llm"), list(prompts))

    def on_llm_new_token(
        self,
        token: str | list[str | dict[str, Any]],
        *,
        chunk: GenerationChunk | ChatGenerationChunk | None = None,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        message = getattr(chunk, "message", None)
        blocks = self._llm_blocks(message) if message is not None else self._llm_token(token)
        pieces = [piece for block in blocks if (piece := self._llm_piece(block))]
        _ = [self._fold.delta(self._common_hex(run_id), part, payload, call_id=call) for part, payload, call in pieces]

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        generation = next(itertools.chain.from_iterable(response.generations), None)
        message = getattr(generation, "message", None)
        blocks = self._llm_blocks(message)
        text = self._llm_join(blocks, "text") or str(getattr(generation, "text", "") or "")
        calls = [
            {"id": call.get("id", ""), "name": call.get("name", ""), "args": call.get("args", {})}
            for call in getattr(message, "tool_calls", None) or []
        ]
        payload = {"text": text, "reasoning": self._llm_join(blocks, "reasoning"), "tool_calls": calls}
        self._fold.close(self._common_hex(run_id), payload, usage=self._llm_usage(message))

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._common_failure(run_id, error)

    ##### TOOLS #####

    def on_tool_start(
        self,
        serialized: dict[str, Any] | None,
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        tool = str(kwargs.get("name") or (serialized or {}).get("name") or "tool")
        args = inputs if inputs is not None else input_str
        call = str(kwargs.get("tool_call_id") or (metadata or {}).get("tool_call_id") or "")
        match (tool in self._subagents, tool in self._mcp):
            case (True, _):
                name = str((inputs or {}).get("subagent_type") or tool)
                self._common_open(
                    run_id, parent_run_id, EventKind.SUBAGENT, name, metadata, call_id=call, payload={"input": args}
                )
            case (_, True):
                self._common_open(
                    run_id, parent_run_id, EventKind.MCP, tool, metadata, call_id=call, payload={"input": args}
                )
            case _:
                self._common_open(
                    run_id, parent_run_id, EventKind.TOOL, tool, metadata, call_id=call, payload={"input": args}
                )

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self._fold.close(self._common_hex(run_id), {"output": getattr(output, "content", output)})

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._common_failure(run_id, error)

    ##### RETRIEVERS #####

    def on_retriever_start(
        self,
        serialized: dict[str, Any] | None,
        query: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        name = str(kwargs.get("name") or (serialized or {}).get("name") or "retriever")
        self._common_open(run_id, parent_run_id, EventKind.RETRIEVAL, name, metadata, payload={"query": query})

    def on_retriever_end(self, documents: Sequence[Any], *, run_id: UUID, **kwargs: Any) -> None:
        found = [
            {"content": getattr(doc, "page_content", ""), "metadata": getattr(doc, "metadata", {})} for doc in documents
        ]
        self._fold.close(self._common_hex(run_id), {"documents": found})

    def on_retriever_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._common_failure(run_id, error)

    ##### CUSTOM #####

    def on_custom_event(self, name: str, data: Any, *, run_id: UUID, **kwargs: Any) -> None:
        """`dispatch_custom_event` from a node or a tool: one CUSTOM frame under the span that dispatched it."""
        span = self._common_hex(run_id)
        edge = Edge(
            id=f"{span}:{name}:{uuid.uuid7().hex}",
            parent=span,
            kind=EventKind.CUSTOM,
            name=name,
            payload={"data": data},
        )
        self._fold.instant(edge)


class LanggraphSourceAdapter:
    """The LangGraph source: `bind` a fold into a `RunnableConfig`; MCP tool names are the host's to declare."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("langgraph", Locality.EMBEDDED, Workload.CPU_BOUND, Isolation.LOOP)

    __slots__ = ("_mcp", "_subagents")

    def __init__(self, mcp: frozenset[str] = frozenset(), subagents: frozenset[str] = SUBAGENTS) -> None:
        self._mcp = mcp
        self._subagents = subagents

    ##### PRIVATE #####

    @staticmethod
    def _bind_callbacks(handler: LanggraphHandler, callbacks: Any) -> Any:
        match callbacks:
            case None:
                return [handler]
            case list():
                return [*callbacks, handler]
            case BaseCallbackManager():
                manager = callbacks.copy()
                manager.add_handler(handler, inherit=True)
                return manager
            case other:
                msg = f"langgraph: callbacks of a RunnableConfig are a list or a manager, not {type(other).__name__}"
                raise SourceError(msg)

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        logger.info("source opened", source="langgraph", mcp=sorted(self._mcp), subagents=sorted(self._subagents))
        return self

    async def __aexit__(self, *exc: object) -> None:
        logger.info("source closed", source="langgraph")

    async def health(self) -> bool:
        """Always ready: the source holds no resource."""
        return True

    def bind(self, fold: FoldPort, scope: RunScope, config: RunnableConfig) -> RunnableConfig:
        """The host's config with the run's handler appended (inherited ones kept) and the run's id as the root's."""
        handler = LanggraphHandler(fold, self._mcp, self._subagents)
        metadata = {
            **(config.get("metadata") or {}),
            "etrack_run_id": scope.run_id,
            "etrack_thread_id": scope.thread_id,
        }
        callbacks = self._bind_callbacks(handler, config.get("callbacks"))
        return RunnableConfig(
            **{**config, "run_id": uuid.UUID(scope.run_id), "metadata": metadata, "callbacks": callbacks}
        )
