"""ChatService: one run per turn, the tracer and the projector on its callbacks, the approval stop surfaced."""

from langchain_core.messages import AIMessage

from deeptrack.models.proposal import Decision
from deeptrack.services.chat import ChatService
from processors.models import EventKind, EventPhase, RunEvent
from processors.projector import EventProjector
from tests.support.fake import FakeTrace


def test_chat_run_config(compiled) -> None:
    run, projector = ChatService(compiled((), AIMessage("x")), FakeTrace(), frozenset()).run("t1", print)
    assert run.trace_id == f"trace-{run.run_id}"
    assert run.config["configurable"] == {"thread_id": "t1"}
    assert run.config["metadata"] == {"session": "t1", "deeptrack_run_id": run.run_id}
    callbacks = run.config["callbacks"]
    assert isinstance(callbacks, list)
    assert isinstance(callbacks[0], EventProjector)
    assert projector is callbacks[0]


async def test_chat_turn_answers(compiled, frames: list[RunEvent]) -> None:
    chat = ChatService(compiled((), AIMessage("Cubre RC y robo.")), FakeTrace(), frozenset())
    turn = await chat.turn("t1", "¿qué cubre pol-1001?", frames.append)
    assert turn.reply == "Cubre RC y robo."
    assert turn.interrupt is None
    assert turn.url == f"http://trace/{turn.trace_id}"
    assert frames[0].kind is EventKind.RUN
    assert frames[0].phase is EventPhase.START
    assert {frame.run_id for frame in frames} == {turn.run_id}


async def test_chat_turn_stops_then_resumes(compiled, proposing, frames: list[RunEvent]) -> None:
    chat = ChatService(compiled((True,), *proposing), FakeTrace(), frozenset())
    stopped = await chat.turn("t1", "denuncia RC pol-1001", frames.append)
    assert stopped.interrupt == {
        "propuesta": {"type": "denuncia", "poliza": "pol-1001", "cobertura": "cob-rc", "fecha_ocurrencia": "2026-07-01"}
    }
    assert frames[-1].kind is EventKind.INTERRUPT
    done = await chat.turn("t1", Decision.APROBAR, frames.append)
    assert done.interrupt is None
    assert done.reply.startswith("Transacción registrada")
    assert done.run_id != stopped.run_id
