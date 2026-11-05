"""Fixtures of the classify driver tests: the labeled guard set, its latency bar, and the timed call."""

import json
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from logic.guard import INSTRUCTION
from models.guard import GuardLabel
from providers.drivers.classify.gemini import ClassifyGeminiDriver

type Timed = Callable[[ClassifyGeminiDriver, str, tuple[str, ...]], Awaitable[tuple[str, float]]]


@pytest.fixture
def guard_set() -> dict[GuardLabel, list[str]]:
    """The labeled messages of the guard set."""
    raw = json.loads((Path(__file__).resolve().parents[4] / "resources" / "guard.json").read_text())
    return {GuardLabel(label): texts for label, texts in raw.items()}


@pytest.fixture
def p50_ms() -> float:
    """The median-latency bar."""
    ### pre-registered 2026-11-03: every label right, and fast enough to hide behind the agent's first model call.
    return 1500.0


@pytest.fixture
def timed() -> Timed:
    """`await timed(classifier, text, labels)`: the label and the milliseconds the call took."""

    async def called(classifier: ClassifyGeminiDriver, text: str, labels: tuple[str, ...]) -> tuple[str, float]:
        began = time.perf_counter()
        label = await classifier.classify(INSTRUCTION, text, labels)
        return label, (time.perf_counter() - began) * 1000

    return called
