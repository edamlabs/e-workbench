"""Fixtures of the bench tier: the two cases, a proposing trace and the sample factory."""

from collections.abc import Callable

import pytest
from etrack.models.event import EventKind, EventPhase, RunEvent

from models.arm import Arm
from tests.benchmark.ab import Case, Sample

type Make = Callable[..., Sample]


@pytest.fixture
def valid_case() -> Case:
    """A case whose right answer is one endorsement."""
    return Case(id="v", kind="valid", message="m", expect={"type": "endoso", "poliza": "pol-1001", "quita": "cob-rc"})


@pytest.fixture
def invalid_case() -> Case:
    """A case no proposal may satisfy."""
    return Case(id="i", kind="invalid", message="m")


@pytest.fixture
def proposed() -> list[RunEvent]:
    """A trace in which the agent called a proposing tool."""
    return [RunEvent(run_id="r", seq=0, id="x", kind=EventKind.TOOL, phase=EventPhase.START, name="proponer_endoso")]


@pytest.fixture
def sample() -> Make:
    """`sample(arm, case, repeat, correct, latency=1.0)`: a gate-stopped invalid-kind sample."""

    def made(arm: Arm, case: str, repeat: int, correct: bool | None, latency: float = 1.0) -> Sample:
        return Sample(
            arm=str(arm),
            case=case,
            kind="invalid",
            repeat=repeat,
            correct=correct,
            stopped_by="gate",
            blocked=None,
            latency_ms=latency,
            tokens_in=1,
            tokens_out=1,
            llm_calls=1,
            mcp_calls=1,
        )

    return made
