"""providers/drivers/chat/google: ChatGoogle — Google's chat model, its stream shaped the way AG-UI's adapter reads it.

Shared by the two Google drivers (Gemini API, Vertex AI); not a provider itself, the model both build.

Gemini sends its last piece of text in the same chunk that carries `finish_reason` (and the usage). ag-ui-langgraph
(0.0.47) returns early on any chunk with a `finish_reason`, assuming the terminal chunk is empty — so the UI never
types that last piece, while the state holds the whole message. Each such chunk is split here: the text first, then
an empty terminal chunk with the finish reason and the usage. The aggregated message is unchanged."""

from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from langchain_google_genai import ChatGoogleGenerativeAI


class ChatGoogle(ChatGoogleGenerativeAI):
    """`ChatGoogleGenerativeAI` whose stream never ends on a chunk that carries both text and a finish reason."""

    @staticmethod
    def _astream_split(chunk: ChatGenerationChunk) -> tuple[ChatGenerationChunk, ...]:
        """A text-bearing final chunk as (text, terminal); any other chunk as itself.

        Inside `_astream` the finish reason still rides `generation_info` (LangChain folds it into the message's
        `response_metadata` later); both places are read and both are moved to the terminal chunk."""
        message, info = chunk.message, chunk.generation_info or {}
        meta = message.response_metadata
        finish = info.get("finish_reason") or meta.get("finish_reason")
        match (finish, bool(message.content), isinstance(message, AIMessageChunk)):
            case (str(), True, True):
                body = message.model_copy(
                    update={
                        "response_metadata": {k: v for k, v in meta.items() if k != "finish_reason"},
                        "usage_metadata": None,
                        "chunk_position": None,
                    }
                )
                terminal = AIMessageChunk(
                    content=[] if isinstance(message.content, list) else "",
                    id=message.id,
                    response_metadata=meta,
                    usage_metadata=getattr(message, "usage_metadata", None),
                    chunk_position=getattr(message, "chunk_position", None),
                )
                return (
                    ChatGenerationChunk(
                        message=body, generation_info={k: v for k, v in info.items() if k != "finish_reason"} or None
                    ),
                    ChatGenerationChunk(message=terminal, generation_info=info or None),
                )
            case _:
                return (chunk,)

    async def aclose(self) -> None:
        """Close the Google client's HTTP pools now, in this loop — left to the GC, it closes them in an orphan task
        after the loop is gone."""
        match self.client:
            case None:
                pass
            case client:
                await client.aio.aclose()
                client.close()

    async def _astream(self, *args: Any, **kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
        async for chunk in super()._astream(*args, **kwargs):
            match self._astream_split(chunk):
                case (body, terminal):
                    yield body
                    yield terminal
                case (whole,):
                    yield whole
