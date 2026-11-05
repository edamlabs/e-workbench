"""InputGuard: one label per message; a non-domain label stops the run; an outage passes the message."""

import pytest
from langchain_core.messages import HumanMessage

from infra.errors import GuardError
from logic.guard import REPLIES, InputGuard
from logic.state import ChatState
from models.guard import GuardLabel
from tests.support.fake import FakeClassifier
from tests.unit.logic.conftest import Said


async def test_guard_passes_domain(said: Said) -> None:
    classifier = FakeClassifier("seguros")
    assert await InputGuard(classifier).run(said("hola", "¿qué cubre pol-1001?"), {}) == {"messages": []}
    assert classifier.seen == ["¿qué cubre pol-1001?"]


@pytest.mark.parametrize("label", [GuardLabel.FUERA_DE_TEMA, GuardLabel.ABUSO])
async def test_guard_stops_the_rest(said: Said, label: GuardLabel) -> None:
    with pytest.raises(GuardError) as stop:
        await InputGuard(FakeClassifier(str(label))).run(said("x"), {})
    assert stop.value.label == label
    assert stop.value.message == REPLIES[label]


async def test_guard_open_on_outage(said: Said) -> None:
    assert await InputGuard(FakeClassifier(down=True)).run(said("x"), {}) == {"messages": []}


async def test_guard_ignores_system_feedback() -> None:
    ### the gate's feedback is a named human message: never what the user said.
    classifier = FakeClassifier("seguros")
    state: ChatState = {
        "messages": [HumanMessage("¿qué cubre pol-1001?"), HumanMessage("[validación] …", name="validador")]
    }
    await InputGuard(classifier).run(state, {})
    assert classifier.seen == ["¿qué cubre pol-1001?"]


async def test_guard_skips_empty() -> None:
    classifier = FakeClassifier("abuso")
    assert await InputGuard(classifier).run({"messages": []}, {}) == {"messages": []}
    assert classifier.seen == []
