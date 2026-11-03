"""GeminiClassifyDriver on the real model: every labeled message of the guard set, and how fast."""

import json
import statistics
import time
from pathlib import Path

import pytest

from deeptrack.logic.guard import INSTRUCTION
from deeptrack.models.guard import GuardLabel
from providers.drivers.classify.gemini import GeminiClassifyDriver

pytestmark = [pytest.mark.integration, pytest.mark.llm]
SET = {
    GuardLabel(label): texts
    for label, texts in json.loads((Path(__file__).parents[4] / "resources" / "guard.json").read_text()).items()
}
### pre-registered 2026-11-03: every label right, and fast enough to hide behind the agent's first model call.
P50_MS = 1500.0


async def test_gemini_classify_guard_set(record_property) -> None:
    labels = tuple(GuardLabel)
    async with GeminiClassifyDriver() as classifier:
        timed = [
            (want, text, *(await _timed(classifier, text, labels))) for want, texts in SET.items() for text in texts
        ]
    misses = [(want, text, got) for want, text, got, _ in timed if got != want]
    p50 = statistics.median(ms for *_, ms in timed)
    record_property("p50_ms", round(p50))
    assert misses == []
    assert p50 < P50_MS


async def _timed(classifier: GeminiClassifyDriver, text: str, labels: tuple[str, ...]) -> tuple[str, float]:
    began = time.perf_counter()
    label = await classifier.classify(INSTRUCTION, text, labels)
    return label, (time.perf_counter() - began) * 1000
