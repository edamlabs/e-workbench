"""Test doubles: a scripted chat model that accepts tools, and an ontology port with a fixed verdict."""

from collections.abc import Iterable, Sequence
from typing import Any, Self

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from deeptrack.models.shacl import ShaclReport, Violation


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


class FakeOnto:
    """The ontology port with scripted verdicts, one per validation, and a record of what it was asked."""

    def __init__(self, verdicts: Iterable[bool] = ()) -> None:
        self._verdicts = iter(verdicts)
        self.validated: list[str] = []

    @property
    def tools(self) -> tuple[BaseTool, ...]:
        return ()

    async def query(self, sparql: str) -> str:
        return '{"results": []}'

    async def validate(self, turtle: str, config: RunnableConfig) -> ShaclReport:
        self.validated.append(turtle)
        conforms = next(self._verdicts)
        broken = (
            ()
            if conforms
            else (Violation(constraint="sparql", focus_node="seg:propuesta", message="fuera de vigencia"),)
        )
        return ShaclReport(conforms=conforms, violation_count=len(broken), violations=broken)
