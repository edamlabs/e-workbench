"""ChatService: one tracked run per turn — etrack's source on its callbacks, the run id its trace id — the stop surfaced."""

import uuid

from etrack.models.event import EventKind, EventPhase
from etrack.providers.adapters.source.langgraph import LanggraphHandler
from langchain_core.messages import AIMessage

from logic.guard import REPLIES
from models.guard import GuardLabel
from models.proposal import Decision
from services.chat import ChatService
from tests.support.fake import FakeClassifier
from tests.support.track import tracked


async def test_chat_run_config(compiled) -> None:
    async with tracked() as (tracker, _recorder):
        with ChatService(compiled((), AIMessage("x")), tracker, "http://trace", {"insurance": "v1"}).run("t1") as run:
            assert (run.trace_id, run.url) == (run.run_id, f"http://trace/{run.run_id}")
            assert run.config["configurable"] == {"thread_id": "t1"}
            assert run.config.get("run_id") == uuid.UUID(run.run_id)
            metadata = run.config["metadata"]
            assert metadata["app.agents"] == {"insurance": "v1"}
            callbacks = run.config["callbacks"]
            assert isinstance(callbacks, list)
            assert isinstance(callbacks[-1], LanggraphHandler)


async def test_chat_turn_answers(compiled) -> None:
    async with tracked() as (tracker, recorder):
        turn = await ChatService(compiled((), AIMessage("Cubre RC y robo.")), tracker, "http://trace").turn(
            "t1", "¿qué cubre pol-1001?"
        )
        frames = await recorder.settled(turn.run_id)
        assert turn.reply == "Cubre RC y robo."
        assert turn.interrupt is None
        assert turn.url == f"http://trace/{turn.trace_id}"
        assert (frames[0].kind, frames[0].phase, frames[0].id) == (EventKind.RUN, EventPhase.START, turn.run_id)
        assert {frame.thread_id for frame in frames} == {"t1"}


async def test_chat_turn_stops_then_resumes(compiled, proposing) -> None:
    async with tracked() as (tracker, recorder):
        chat = ChatService(compiled((True,), *proposing), tracker)
        stopped = await chat.turn("t1", "denuncia RC pol-1001")
        assert stopped.interrupt == {
            "propuesta": {
                "type": "denuncia",
                "poliza": "pol-1001",
                "cobertura": "cob-rc",
                "fecha_ocurrencia": "2026-07-01",
            }
        }
        (stop,) = [frame for frame in await recorder.settled(stopped.run_id) if frame.kind is EventKind.INTERRUPT]
        assert stop.payload["value"] == [stopped.interrupt]
        done = await chat.turn("t1", Decision.APROBAR)
        assert done.interrupt is None
        assert done.reply.startswith("Transacción registrada")
        assert done.run_id != stopped.run_id


async def test_chat_guard_stops_the_whole_run(compiled, proposing) -> None:
    async with tracked() as (tracker, recorder):
        graph = compiled((True,), *proposing, guard=FakeClassifier("abuso"))
        turn = await ChatService(graph, tracker).turn("t1", "insulto")
        assert turn.blocked == "abuso"
        assert turn.reply == REPLIES[GuardLabel.ABUSO]
        state = await graph.aget_state({"configurable": {"thread_id": "t1"}})
        ### the input is recorded before the step; nothing of the agent's step was committed — no reply, no proposal.
        assert [each.text for each in state.values["messages"]] == ["insulto"]
        assert "propuesta" not in state.values
        assert state.interrupts == ()
        assert [f for f in await recorder.settled(turn.run_id) if f.name == "guard" and f.phase is EventPhase.ERROR]


async def test_chat_guard_cancels_a_slower_agent(compiled, proposing) -> None:
    async with tracked() as (tracker, recorder):
        ### the guard answers after the agent has begun: the step still fails whole, the gate never runs.
        graph = compiled((True,), *proposing, guard=FakeClassifier("fuera_de_tema", delay=0.05))
        turn = await ChatService(graph, tracker).turn("t2", "dame código")
        assert turn.blocked == "fuera_de_tema"
        assert not [f for f in await recorder.settled(turn.run_id) if f.name == "gate"]
