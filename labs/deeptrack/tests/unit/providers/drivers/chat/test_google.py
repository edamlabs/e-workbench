"""ChatGoogle's stream split: a final chunk that carries text is cut into the text and an empty terminal chunk."""

import functools
import operator

from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

from providers.drivers.chat.google import ChatGoogle

USAGE = {"input_tokens": 3, "output_tokens": 5, "total_tokens": 8}


def usage(part: ChatGenerationChunk) -> object:
    """The chunk's usage: generation chunks are typed by the base message chunk, which does not declare it."""
    return getattr(part.message, "usage_metadata", None)


def chunk(text: str, finish: str | None = None) -> ChatGenerationChunk:
    blocks = [{"type": "text", "text": text, "index": 0}] if text else []
    usage = USAGE if finish else None
    return ChatGenerationChunk(
        message=AIMessageChunk(content=blocks, usage_metadata=usage),
        generation_info={"finish_reason": finish} if finish else None,
    )


def test_google_split_final_text_chunk() -> None:
    body, terminal = ChatGoogle._astream_split(chunk(" coberturas.", "STOP"))
    assert body.message.text == " coberturas."
    assert "finish_reason" not in (body.generation_info or {})
    assert usage(body) is None
    assert terminal.message.text == ""
    assert terminal.generation_info == {"finish_reason": "STOP"}
    assert usage(terminal) == USAGE


def test_google_split_leaves_other_chunks() -> None:
    assert len(ChatGoogle._astream_split(chunk("La póliza"))) == 1
    assert len(ChatGoogle._astream_split(chunk("", "STOP"))) == 1


def test_google_split_keeps_the_aggregate() -> None:
    stream = [chunk("La póliza"), chunk(" cubre RC.", "STOP")]
    split = [part for each in stream for part in ChatGoogle._astream_split(each)]
    whole, again = functools.reduce(operator.add, stream), functools.reduce(operator.add, split)
    assert again.message.text == whole.message.text
    assert usage(again) == usage(whole)
    assert again.generation_info == whole.generation_info
