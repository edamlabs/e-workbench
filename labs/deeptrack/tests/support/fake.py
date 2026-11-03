"""Test doubles: a scripted chat model and its provider, and an ontology server with scripted SHACL verdicts."""

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, ClassVar, Self

from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from ports.provider import Isolation, Locality, ProviderSpec, Workload


class ScriptedModel(GenericFakeChatModel):
    """Answers with the scripted messages in order; tools are accepted and ignored — the script already calls them."""

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Self:
        return self


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
