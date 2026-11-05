"""ChatGoogle's stream split: a final chunk that carries text is cut into the text and an empty terminal chunk."""

import functools
import operator

from providers.drivers.chat.google import ChatGoogle
from tests.unit.providers.drivers.chat.conftest import Chunk, Usage


async def test_google_split_final_text_chunk(chunk: Chunk, usage: Usage, totals: dict[str, int]) -> None:
    body, terminal = ChatGoogle._astream_split(chunk(" coberturas.", "STOP"))
    assert body.message.text == " coberturas."
    assert "finish_reason" not in (body.generation_info or {})
    assert usage(body) is None
    assert terminal.message.text == ""
    assert terminal.generation_info == {"finish_reason": "STOP"}
    assert usage(terminal) == totals


async def test_google_split_leaves_other_chunks(chunk: Chunk) -> None:
    assert len(ChatGoogle._astream_split(chunk("La póliza"))) == 1
    assert len(ChatGoogle._astream_split(chunk("", "STOP"))) == 1


async def test_google_split_keeps_the_aggregate(chunk: Chunk, usage: Usage) -> None:
    stream = [chunk("La póliza"), chunk(" cubre RC.", "STOP")]
    split = [part for each in stream for part in ChatGoogle._astream_split(each)]
    whole, again = functools.reduce(operator.add, stream), functools.reduce(operator.add, split)
    assert again.message.text == whole.message.text
    assert usage(again) == usage(whole)
    assert again.generation_info == whole.generation_info
