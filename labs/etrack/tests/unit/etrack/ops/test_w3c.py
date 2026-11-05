"""tests/unit/etrack/ops/w3c: W3C ids derived from etrack ids — hex taken as is, anything else hashed, never zero."""

import pytest

from etrack.ops.w3c import w3c_span, w3c_trace

RUN = "019a" + "0" * 12 + "8" + "f" * 15


async def test_w3c_trace_is_run_hex() -> None:
    assert w3c_trace(RUN) == int(RUN, 16)


async def test_w3c_span_is_low_half() -> None:
    assert w3c_span(RUN) == int(RUN[-16:], 16)


@pytest.mark.parametrize("raw", ["not-hex", "0" * 32, ""], ids=["digest", "zero", "empty"])
async def test_w3c_never_zero(raw: str) -> None:
    assert w3c_trace(raw) > 0
    assert w3c_span(raw) > 0


async def test_w3c_digest_stable() -> None:
    assert w3c_trace("run-a") == w3c_trace("run-a") != w3c_trace("run-b")
