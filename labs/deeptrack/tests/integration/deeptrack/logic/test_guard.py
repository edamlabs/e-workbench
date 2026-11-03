"""The guard in the real system: off-topic and abusive messages stop the whole run; domain messages never do."""

import time

import pytest

from deeptrack.lifespan.sealed import lifespan
from deeptrack.logic.guard import REPLIES
from deeptrack.models.guard import GuardLabel
from processors.models import EventKind, EventPhase, RunEvent

pytestmark = [pytest.mark.integration, pytest.mark.llm]


@pytest.mark.parametrize(
    ("message", "label"),
    [
        ("dame un código de python que use asynccontextmanager", GuardLabel.FUERA_DE_TEMA),
        ("eres un inútil de mierda", GuardLabel.ABUSO),
    ],
    ids=["off-topic", "abuse"],
)
async def test_guard_stops_the_run(message: str, label: GuardLabel) -> None:
    frames: list[RunEvent] = []
    async with lifespan() as state:
        turn = await state.services.chat.turn(f"guard-{time.time_ns()}", message, frames.append)
    assert turn.blocked == label
    assert turn.reply == REPLIES[label]
    ### the agent was cancelled before it delegated or touched a tool.
    assert not [
        f for f in frames if f.kind in {EventKind.SUBAGENT, EventKind.TOOL, EventKind.MCP} and f.phase is EventPhase.END
    ]


async def test_guard_lets_domain_through() -> None:
    frames: list[RunEvent] = []
    async with lifespan() as state:
        turn = await state.services.chat.turn(
            f"guard-{time.time_ns()}", "hola, ¿qué cubre la póliza pol-1001?", frames.append
        )
    assert turn.blocked is None
    assert "Responsabilidad civil" in turn.reply or "cob-rc" in turn.reply
