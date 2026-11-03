"""LangfuseTraceDriver against the lab's Langfuse: the generated keys authenticate, wrong keys do not."""

import pytest

from infra.config.base import Secret
from infra.settings import settings as st
from providers.drivers.trace.langfuse import LangfuseTraceDriver

pytestmark = pytest.mark.integration


async def test_langfuse_keys_authenticate() -> None:
    async with LangfuseTraceDriver() as trace:
        assert await trace.health()


async def test_langfuse_wrong_keys_unhealthy() -> None:
    ### the SDK keeps one client per public key: a wrong pair needs its own public key too.
    wrong = st.providers.drivers.trace.langfuse.model_copy(
        update={"public_key": "pk-lf-wrong", "secret_key": Secret("sk-lf-wrong")}
    )
    async with LangfuseTraceDriver(wrong) as trace:
        assert not await trace.health()
