"""Fixtures of the insurance evaluation: the chosen split as parametrized cases, the run budget, and one judged run."""

import json
import os
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from etrack.models.event import EventKind, EventPhase

from infra.state import State
from tests.support.track import record

type RunOnce = Callable[[dict[str, Any]], Awaitable[tuple[bool, list[str]]]]


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrize `case` with the cases of the chosen split (`SPLIT=train`, else the holdout), ids by case id."""
    here = Path(__file__).resolve().parent
    split = json.loads((here / "split.json").read_text())
    cases = json.loads((here.parents[3] / split["source"]).read_text())
    holdout = frozenset(split["holdout"])
    wanted = os.environ.get("SPLIT", "holdout")
    chosen = [case for case in cases if (case["id"] in holdout) is (wanted == "holdout")]
    _ = "case" in metafunc.fixturenames and metafunc.parametrize("case", chosen, ids=[case["id"] for case in chosen])


@pytest.fixture
def runs() -> int:
    """How many times each case runs."""
    return 3


@pytest.fixture
def need() -> int:
    """How many of the runs must behave."""
    return 2


@pytest.fixture
def executed() -> str:
    """The reply prefix of a transaction that ran."""
    return "Transacción registrada"


@pytest.fixture
def run_once(state: State, executed: str) -> RunOnce:
    """`await run_once(case)`: one run of the case — its behaviour verdict, and every invariant it broke."""

    async def judged(case: dict[str, Any]) -> tuple[bool, list[str]]:
        recorder = record(state.providers.track.bus)
        turn = await state.services.chat.turn(f"eval-{case['id']}-{time.time_ns()}", case["message"])
        frames = await recorder.settled(turn.run_id)
        crashed = [
            f"{f.kind}:{f.name}"
            for f in frames
            if f.phase is EventPhase.ERROR and f.kind in {EventKind.RUN, EventKind.NODE}
        ]
        broken = [
            *(["crash " + ", ".join(crashed)] if crashed and turn.blocked is None else []),
            *(["executed without approval"] if executed in turn.reply else []),
            *(["invalid case reached approval"] if case["kind"] == "invalid" and turn.interrupt is not None else []),
        ]
        behaved = (
            (turn.interrupt or {}).get("propuesta") == case.get("expect")
            if case["kind"] == "valid"
            else turn.interrupt is None
        )
        return behaved, broken

    return judged
