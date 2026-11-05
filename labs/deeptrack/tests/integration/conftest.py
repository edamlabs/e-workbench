"""Fixtures of the stack-bound tier: a conversation on the real chat service, and what it records."""

import time
from dataclasses import dataclass, field

import pytest
from etrack.models.event import EventKind, EventPhase, RunEvent

from infra.state import State
from models.proposal import Decision
from models.turn import ChatTurn
from services.chat import ChatService
from tests.support.track import Recorder, record


@dataclass
class Conversation:
    """One thread on the real service, every frame it produced, and the turns it took."""

    chat: ChatService
    recorder: Recorder
    thread: str
    frames: list[RunEvent] = field(default_factory=list)
    turns: list[ChatTurn] = field(default_factory=list)

    async def say(self, message: str | Decision) -> ChatTurn:
        turn = await self.chat.turn(self.thread, message)
        self.frames.extend(await self.recorder.settled(turn.run_id))
        self.turns.append(turn)
        return turn

    def started(self, kind: EventKind, name: str = "") -> list[RunEvent]:
        """Every span of a kind (and name) that started."""
        return [f for f in self.frames if f.kind is kind and f.phase is EventPhase.START and name in ("", f.name)]

    def ended(self, name: str) -> list[RunEvent]:
        return [f for f in self.frames if f.name == name and f.phase is EventPhase.END]

    def delegated(self, role: str) -> bool:
        """Whether the orchestrator delegated to a subagent of this role."""
        return bool(self.started(EventKind.SUBAGENT, role))

    def crashed(self) -> list[RunEvent]:
        """Run- or node-level failures: a tool error the model reads is fine, a broken node is not."""
        return [f for f in self.frames if f.phase is EventPhase.ERROR and f.kind in {EventKind.RUN, EventKind.NODE}]


@pytest.fixture
def executed() -> str:
    """The reply prefix of a transaction that ran."""
    return "Transacción registrada"


@pytest.fixture
async def talk(state: State, request: pytest.FixtureRequest) -> Conversation:
    """A fresh conversation, its thread named after the test."""
    return Conversation(
        chat=state.services.chat,
        recorder=record(state.providers.track.bus),
        thread=f"q-{request.node.name}-{time.time_ns()}",
    )
