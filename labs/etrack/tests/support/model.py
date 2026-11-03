"""tests/support/model: a chat model that says exactly what a test scripts, streamed like a real provider."""

import json
from typing import TYPE_CHECKING, Any, Self

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGenerationChunk

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from langchain_core.callbacks import CallbackManagerForLLMRun


class ScriptedModel(GenericFakeChatModel):
    """Answers with the scripted messages in order; tools are accepted and ignored — the script already calls them.

    One chunk per message, content blocks (reasoning, text) and tool calls together, usage on the chunk: the stock fake
    streams nothing for a tool-call-only message, which is what an agent's model mostly says."""

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
        chunk = ChatGenerationChunk(
            message=AIMessageChunk(
                content=message.content, tool_call_chunks=calls, usage_metadata=message.usage_metadata
            )
        )
        _ = run_manager and run_manager.on_llm_new_token(message.text, chunk=chunk)
        yield chunk


def script(*messages: AIMessage | str) -> ScriptedModel:
    """A model that says exactly these messages, one per call."""
    return ScriptedModel(messages=iter(messages))


def call(name: str, call_id: str, **args: Any) -> AIMessage:
    """A model turn that calls one tool."""
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])


def think(reasoning: str, text: str, **usage: int) -> AIMessage:
    """A model turn that reasons, then answers, and reports what it spent."""
    spent = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, **usage} if usage else None
    blocks: list[str | dict[str, Any]] = [{"type": "reasoning", "reasoning": reasoning}, {"type": "text", "text": text}]
    return AIMessage(content=blocks, usage_metadata=spent)
