"""The frames of a scripted proposing turn: ordered, parented, classified, closed."""

from collections import Counter

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver

from deeptrack.logic.agent import InsuranceAgent
from deeptrack.logic.gate import ShaclGate
from deeptrack.logic.graph import ChatGraph
from engines.shacl import ShaclEngine
from processors.models import EventKind, EventPhase, RunEvent
from processors.projector import EventProjector
from tests.support.fake import FakeOntology, script


def ancestors(span: str, by_id: dict[str, RunEvent]) -> tuple[str, ...]:
    """Every span above `span`, nearest first."""
    parent = by_id[span].parent if span in by_id else ""
    return (parent, *ancestors(parent, by_id)) if parent else ()


async def run_frames(proposing, frames: list[RunEvent]) -> list[RunEvent]:
    engine = ShaclEngine(FakeOntology([True]), base=(), shapes="shapes")
    graph = ChatGraph(InsuranceAgent(script(*proposing), FakeOntology()).build(), ShaclGate(engine)).build(
        InMemorySaver()
    )
    projector = EventProjector("run", "trace", frames.append)
    config: RunnableConfig = {"configurable": {"thread_id": "t"}, "callbacks": [projector], "recursion_limit": 80}
    await graph.ainvoke({"messages": [("user", "denuncia RC pol-1001")]}, config)
    projector.interrupt((await graph.aget_state(config)).interrupts[0].value)
    return frames


async def test_projector_order_and_parents(proposing, frames) -> None:
    seen = await run_frames(proposing, frames)
    assert [frame.seq for frame in seen] == list(range(len(seen)))
    ids = {frame.id for frame in seen}
    assert all(frame.parent in ids for frame in seen if frame.kind is not EventKind.RUN)
    assert seen[0].kind is EventKind.RUN
    assert seen[0].phase is EventPhase.START


async def test_projector_spans_balanced(proposing, frames) -> None:
    seen = await run_frames(proposing, frames)
    starts = Counter(
        frame.id for frame in seen if frame.phase is EventPhase.START and frame.kind is not EventKind.INTERRUPT
    )
    ends = Counter(frame.id for frame in seen if frame.phase in {EventPhase.END, EventPhase.ERROR})
    assert starts == ends


async def test_projector_classifies_tree(proposing, frames) -> None:
    seen = await run_frames(proposing, frames)
    by_id = {frame.id: frame for frame in seen}
    subagent = next(frame for frame in seen if frame.kind is EventKind.SUBAGENT)
    proposal = next(frame for frame in seen if frame.name == "proponer_denuncia")
    assert subagent.id in ancestors(proposal.id, by_id)
    assert {"agent", "gate", "approval"} <= {frame.name for frame in seen if frame.kind is EventKind.NODE}
    assert seen[-1].kind is EventKind.INTERRUPT
    assert any(frame.payload.get("interrupted") for frame in seen if frame.name == "approval")
