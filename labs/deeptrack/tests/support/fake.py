"""Test doubles: a scripted chat model and its provider, and an ontology server with scripted SHACL verdicts."""

import asyncio
import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import Any, ClassVar, Self

from langchain_core.callbacks import BaseCallbackHandler, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGenerationChunk
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool

from infra.errors import ModelError
from ports.provider import Isolation, Locality, ProviderSpec, Workload


class ScriptedModel(GenericFakeChatModel):
    """Answers with the scripted messages in order; tools are accepted and ignored — the script already calls them.

    Streams like a real provider: one chunk per message, text and tool calls together (the stock fake streams nothing
    for a tool-call-only message, which is exactly what an agent's model mostly says)."""

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Self:
        return self

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        said = next(self.messages)
        message = AIMessage(said) if isinstance(said, str) else said
        calls = [
            {
                "name": call["name"],
                "args": json.dumps(call["args"]),
                "id": call["id"],
                "index": index,
                "type": "tool_call_chunk",
            }
            for index, call in enumerate(message.tool_calls)
        ]
        chunk = ChatGenerationChunk(message=AIMessageChunk(content=message.content, tool_call_chunks=calls))
        run_manager.on_llm_new_token(message.text, chunk=chunk) if run_manager else None
        yield chunk


def script(*messages: AIMessage | str) -> ScriptedModel:
    """A model that says exactly these messages, one per call."""
    return ScriptedModel(messages=iter(messages))


def call(name: str, call_id: str, **args: Any) -> AIMessage:
    """A model turn that calls one tool."""
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])


class ScriptedChat:
    """A `ChatPort` provider over a scripted model: the lifespan opens it like Vertex, no credentials."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("scripted", Locality.EMBEDDED, Workload.CPU_BOUND, Isolation.LOOP)

    def __init__(self, *messages: AIMessage | str) -> None:
        self._model = script(*messages)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def health(self) -> bool:
        return True

    @property
    def model(self) -> BaseChatModel:
        return self._model


class FakeOntology:
    """An `OntologyPort` with no tools: every call recorded, `onto_shacl` answered from the scripted verdicts."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("fake", Locality.EMBEDDED, Workload.CPU_BOUND, Isolation.LOOP)

    def __init__(self, verdicts: Iterable[bool] = ()) -> None:
        self._verdicts = iter(verdicts)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def health(self) -> bool:
        return True

    @property
    def tools(self) -> Mapping[str, BaseTool]:
        return {}

    async def call(self, tool: str, args: Mapping[str, Any], config: RunnableConfig | None = None) -> str:
        self.calls.append((tool, dict(args)))
        match tool:
            case "onto_shacl":
                conforms = next(self._verdicts)
                broken = (
                    []
                    if conforms
                    else [{"constraint": "sparql", "focus_node": "seg:propuesta", "message": "fuera de vigencia"}]
                )
                return json.dumps({"conforms": conforms, "violation_count": len(broken), "violations": broken})
            case _:
                return "{}"


class FakeTrace:
    """A `TracePort` that records nothing: derived ids, a handler that listens to nothing, a session marker."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("fake", Locality.EMBEDDED, Workload.CPU_BOUND, Isolation.LOOP)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def health(self) -> bool:
        return True

    def trace_id(self, run_id: str) -> str:
        return f"trace-{run_id}"

    def handler(self, run_id: str) -> BaseCallbackHandler:
        return BaseCallbackHandler()

    def url(self, trace_id: str) -> str:
        return f"http://trace/{trace_id}"

    def session(self, thread: str) -> dict[str, str]:
        return {"session": thread}

    async def flush(self) -> None:
        return None


class ToolOntology(FakeOntology):
    """A fake ontology server that advertises tools by name — what the agent's whitelist filters."""

    def __init__(self, names: Iterable[str]) -> None:
        super().__init__()
        self._tools = {
            name: StructuredTool.from_function(func=lambda: "", name=name, description=name) for name in names
        }

    @property
    def tools(self) -> Mapping[str, BaseTool]:
        return self._tools


class FakeClassifier:
    """A `ClassifyPort` that answers a fixed label after an optional delay, or fails like an outage."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("fake", Locality.EMBEDDED, Workload.CPU_BOUND, Isolation.LOOP)

    def __init__(self, label: str = "seguros", delay: float = 0.0, *, down: bool = False) -> None:
        self._label = label
        self._delay = delay
        self._down = down
        self.seen: list[str] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def health(self) -> bool:
        return not self._down

    async def classify(
        self, system: str, text: str, labels: tuple[str, ...], config: RunnableConfig | None = None
    ) -> str:
        self.seen.append(text)
        await asyncio.sleep(self._delay)
        match self._down:
            case True:
                msg = "classifier down"
                raise ModelError(msg)
            case False:
                return self._label
