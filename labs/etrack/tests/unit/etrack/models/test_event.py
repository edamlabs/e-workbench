"""tests/unit/etrack/models/event: the record, its derived ids, its views and how it grows."""

from typing import Any

import msgspec
import pytest

from etrack.models.event import VERSION, EventKind, EventPhase, EventView, LogView, Part, RunEvent, Usage
from unit.etrack.conftest import RUN, frame


async def test_runevent_defaults() -> None:
    event = frame()
    assert (event.v, event.parent, event.part, event.payload, event.attributes) == (VERSION, "", None, {}, {})
    assert event.at.tzinfo is not None


async def test_runevent_trace_id_is_run_id() -> None:
    assert frame().trace_id == RUN


async def test_runevent_dedupe_key() -> None:
    assert frame(3, EventPhase.END).dedupe_key == f"{RUN}:s3:end:3"


async def test_runevent_roundtrip() -> None:
    event = frame(2, EventPhase.DELTA, kind=EventKind.LLM, part=Part.REASONING, usage=Usage(input_tokens=4))
    assert msgspec.json.decode(msgspec.json.encode(event), type=RunEvent) == event


async def test_runevent_frozen() -> None:
    with pytest.raises(AttributeError):
        frame().seq = 9  # ty: ignore[invalid-assignment]


async def test_runevent_rejects_unknown_kind() -> None:
    raw: dict[str, Any] = {"run_id": RUN, "seq": 0, "id": "s", "kind": "planet", "phase": "start"}
    with pytest.raises(msgspec.ValidationError):
        msgspec.convert(raw, RunEvent)


@pytest.mark.parametrize("kind", list(EventKind), ids=[str(kind) for kind in EventKind])
async def test_runevent_every_kind_encodes(kind: EventKind) -> None:
    assert msgspec.json.decode(msgspec.json.encode(frame(kind=kind)), type=RunEvent).kind is kind


async def test_logview_project_leaves_payload() -> None:
    line = LogView.project(frame(payload={"secret": "x"}, attributes={"a": 1}))
    assert not hasattr(line, "payload")
    assert (line.run_id, line.kind) == (RUN, EventKind.NODE)


async def test_eventview_project_custom() -> None:
    class ChatView(EventView, frozen=True, kw_only=True):
        message_id: str = ""
        part: Part | None = None

    view = ChatView.project(frame(message_id="m1", part=Part.TEXT))
    assert (view.message_id, view.part) == ("m1", Part.TEXT)


async def test_runevent_subclass_grows() -> None:
    class AguiEvent(RunEvent, frozen=True, kw_only=True):
        agui_type: str = ""

    grown = AguiEvent(**msgspec.structs.asdict(frame()), agui_type="STEP_STARTED")
    assert LogView.project(grown).id == "s0"
    assert RunEvent.project(grown).id == "s0"
