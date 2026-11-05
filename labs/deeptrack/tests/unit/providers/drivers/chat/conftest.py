"""Fixtures of the chat driver: generation chunks as the stream yields them, and their usage."""

from collections.abc import Callable

import pytest
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

type Usage = Callable[[ChatGenerationChunk], object]
type Chunk = Callable[..., ChatGenerationChunk]


@pytest.fixture
def totals() -> dict[str, int]:
    """The usage a final chunk carries."""
    return {"input_tokens": 3, "output_tokens": 5, "total_tokens": 8}


@pytest.fixture
def usage() -> Usage:
    """`usage(part)`: the chunk's usage — generation chunks are typed by the base message chunk, which does not declare it."""
    return lambda part: getattr(part.message, "usage_metadata", None)


@pytest.fixture
def chunk(totals: dict[str, int]) -> Chunk:
    """`chunk(text, finish=None)`: a text chunk, final (with usage and finish reason) when `finish` is given."""

    def made(text: str, finish: str | None = None) -> ChatGenerationChunk:
        blocks = [{"type": "text", "text": text, "index": 0}] if text else []
        return ChatGenerationChunk(
            message=AIMessageChunk(content=blocks, usage_metadata=totals if finish else None),
            generation_info={"finish_reason": finish} if finish else None,
        )

    return made
