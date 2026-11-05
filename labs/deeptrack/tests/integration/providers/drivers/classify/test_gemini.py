"""ClassifyGeminiDriver on the real model: every labeled message of the guard set, and how fast."""

import statistics

import pytest

from infra.settings import settings as st
from models.guard import GuardLabel
from providers.drivers.classify.gemini import ClassifyGeminiDriver
from tests.integration.providers.drivers.classify.conftest import Timed

pytestmark = [pytest.mark.integration, pytest.mark.llm]


async def test_gemini_classify_guard_set(
    record_property, guard_set: dict[GuardLabel, list[str]], p50_ms: float, timed: Timed
) -> None:
    labels = tuple(GuardLabel)
    async with ClassifyGeminiDriver(
        ref=st.DEEPTRACK_CLASSIFY_REF,
        api_key=st.GEMINI_API_KEY,
        thinking=st.DEEPTRACK_CLASSIFY_THINKING_LEVEL,
        timeout=st.DEEPTRACK_CLASSIFY_TIMEOUT,
    ) as classifier:
        results = [
            (want, text, *(await timed(classifier, text, labels)))
            for want, texts in guard_set.items()
            for text in texts
        ]
    misses = [(want, text, got) for want, text, got, _ in results if got != want]
    p50 = statistics.median(ms for *_, ms in results)
    record_property("p50_ms", round(p50))
    assert misses == []
    assert p50 < p50_ms
