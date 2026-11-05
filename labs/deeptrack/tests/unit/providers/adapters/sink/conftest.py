"""Fixtures of the sink adapters: run events as the tracker emits them."""

from collections.abc import Callable
from typing import Any

import pytest
from etrack.models.event import EventKind, EventPhase, RunEvent

type Frame = Callable[..., RunEvent]


@pytest.fixture
def frame() -> Frame:
    """`frame(seq, span, parent, kind, phase, **fields)`: one event of run `r`."""

    def made(seq: int, span: str, parent: str, kind: EventKind, phase: EventPhase, **fields: Any) -> RunEvent:
        return RunEvent(run_id="r", seq=seq, id=span, parent=parent, kind=kind, phase=phase, name=str(kind), **fields)

    return made
