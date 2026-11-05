"""tests/unit/etrack/processors/fold: edges folded into frames — parents, seq, visits, latency, redaction, spans."""

from typing import Any

import pytest

from etrack.models.event import EventKind, EventPhase, Failure, Part, RunEvent, RunScope, Usage
from etrack.ports.source import Edge, FoldPort
from etrack.processors.fold import FoldProcessor
from unit.etrack.conftest import RUN

SCOPE = RunScope(run_id=RUN, thread_id="t1")


@pytest.fixture
def emitted() -> list[RunEvent]:
    return []


@pytest.fixture
def fold(emitted: list[RunEvent]) -> FoldProcessor:
    return FoldProcessor(SCOPE, emitted.append)


def edge(span: str, parent: str = "", kind: EventKind | None = EventKind.NODE, **fields: Any) -> Edge:
    return Edge(id=span, parent=parent, kind=kind, name=fields.pop("name", span), **fields)


async def test_fold_meets_port(fold: FoldProcessor) -> None:
    assert isinstance(fold, FoldPort)


async def test_fold_root_and_scope(fold: FoldProcessor, emitted: list[RunEvent]) -> None:
    fold.open(edge("r", kind=EventKind.RUN))
    assert fold.root == "r"
    assert fold.scope is SCOPE
    assert (emitted[0].run_id, emitted[0].thread_id, emitted[0].parent) == (RUN, "t1", "")


async def test_fold_plumbing_folds_into_ancestor(fold: FoldProcessor, emitted: list[RunEvent]) -> None:
    fold.open(edge("r", kind=EventKind.RUN))
    fold.open(edge("seq", "r", kind=None))
    fold.open(edge("n", "seq"))
    fold.close("seq", {})
    assert [event.id for event in emitted] == ["r", "n"]
    assert emitted[1].parent == "r"


async def test_fold_unknown_parent_hangs_from_root(fold: FoldProcessor, emitted: list[RunEvent]) -> None:
    fold.open(edge("r", kind=EventKind.RUN))
    fold.open(edge("n", "never-seen"))
    assert emitted[1].parent == "r"


async def test_fold_seq_contiguous(fold: FoldProcessor, emitted: list[RunEvent]) -> None:
    fold.open(edge("r", kind=EventKind.RUN))
    fold.open(edge("n", "r"))
    fold.delta("n", Part.TEXT, {"delta": "x"})
    fold.close("n", {})
    fold.close("r", {})
    assert [event.seq for event in emitted] == [0, 1, 2, 3, 4]


async def test_fold_visits_count_per_node(fold: FoldProcessor, emitted: list[RunEvent]) -> None:
    fold.open(edge("r", kind=EventKind.RUN))
    _ = [(fold.open(edge(f"a{index}", "r", name="agent")), fold.close(f"a{index}", {})) for index in range(3)]
    starts = [event.visit for event in emitted if event.phase is EventPhase.START and event.kind is EventKind.NODE]
    assert starts == [1, 2, 3]
    assert emitted[0].visit is None


async def test_fold_close_latency_usage(fold: FoldProcessor, emitted: list[RunEvent]) -> None:
    fold.open(edge("m", kind=EventKind.LLM))
    fold.close("m", {"text": "hi"}, usage=Usage(input_tokens=2))
    end = emitted[-1]
    assert (end.phase, end.usage, end.payload) == (EventPhase.END, Usage(input_tokens=2), {"text": "hi"})
    assert end.latency_ms is not None
    assert end.latency_ms >= 0


async def test_fold_close_error(fold: FoldProcessor, emitted: list[RunEvent]) -> None:
    fold.open(edge("t", kind=EventKind.TOOL))
    fold.close("t", {}, error=Failure(type="ValueError", message="bad"))
    assert (emitted[-1].phase, emitted[-1].error) == (EventPhase.ERROR, Failure(type="ValueError", message="bad"))


@pytest.mark.parametrize("span", ["never", "closed"], ids=["unknown", "twice"])
async def test_fold_close_ignored(fold: FoldProcessor, emitted: list[RunEvent], span: str) -> None:
    fold.open(edge("closed"))
    fold.close("closed", {})
    fold.close(span, {})
    assert len(emitted) == 2


async def test_fold_delta_closed_dropped(fold: FoldProcessor, emitted: list[RunEvent]) -> None:
    fold.open(edge("m", kind=EventKind.LLM))
    fold.close("m", {})
    fold.delta("m", Part.TEXT, {"delta": "late"})
    assert len(emitted) == 2


async def test_fold_llm_message_id(fold: FoldProcessor, emitted: list[RunEvent]) -> None:
    fold.open(edge("m", kind=EventKind.LLM))
    fold.delta("m", Part.TEXT, {"delta": "a"})
    fold.open(edge("t", kind=EventKind.TOOL, call_id="c1"))
    assert [event.message_id for event in emitted] == ["m", "m", ""]
    assert emitted[-1].call_id == "c1"


async def test_fold_delta_call_id(fold: FoldProcessor, emitted: list[RunEvent]) -> None:
    fold.open(edge("m", kind=EventKind.LLM))
    fold.delta("m", Part.TOOL_CALL, {"delta": "{}"}, call_id="c9")
    assert (emitted[-1].part, emitted[-1].call_id) == (Part.TOOL_CALL, "c9")


async def test_fold_instant_parents(fold: FoldProcessor, emitted: list[RunEvent]) -> None:
    fold.open(edge("r", kind=EventKind.RUN))
    fold.open(edge("n", "r"))
    fold.close("n", {})
    fold.instant(edge("i", "n", kind=EventKind.INTERRUPT))
    fold.instant(edge("s", kind=EventKind.STATE))
    assert [(event.phase, event.parent) for event in emitted[-2:]] == [
        (EventPhase.INSTANT, "n"),
        (EventPhase.INSTANT, "r"),
    ]


async def test_fold_redacts_every_payload(emitted: list[RunEvent]) -> None:
    fold = FoldProcessor(SCOPE, emitted.append, redact=lambda payload: dict.fromkeys(payload, "***"))
    fold.open(edge("m", kind=EventKind.LLM, payload={"input": "secret"}))
    fold.delta("m", Part.TEXT, {"delta": "secret"})
    fold.close("m", {"text": "secret"})
    assert [event.payload for event in emitted] == [{"input": "***"}, {"delta": "***"}, {"text": "***"}]


async def test_fold_keep_identity() -> None:
    payload = {"a": 1}
    assert FoldProcessor._common_keep(payload) is payload


async def test_fold_span_ok(fold: FoldProcessor, emitted: list[RunEvent]) -> None:
    fold.open(edge("r", kind=EventKind.RUN))
    with fold.span("gate", kind=EventKind.EVALUATION, payload={"rule": "shacl"}) as span:
        pass
    assert [(event.id, event.phase, event.parent) for event in emitted[1:]] == [
        (span, EventPhase.START, "r"),
        (span, EventPhase.END, "r"),
    ]
    assert emitted[1].payload == {"rule": "shacl"}


async def test_fold_span_error(fold: FoldProcessor, emitted: list[RunEvent]) -> None:
    msg = "boom"
    with pytest.raises(RuntimeError, match=msg), fold.span("work"):
        raise RuntimeError(msg)
    assert (emitted[-1].phase, emitted[-1].error) == (EventPhase.ERROR, Failure(type="RuntimeError", message=msg))
