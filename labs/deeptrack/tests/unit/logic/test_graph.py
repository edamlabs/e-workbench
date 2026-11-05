"""The outer graph's routes, driven by a scripted model: no proposal, approve, reject, violation."""

import pytest
from etrack.providers.adapters.topology.langgraph import LanggraphTopologyAdapter
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from logic.graph import AGENT_STAGES, STAGES, ChatGraph
from models.proposal import Decision
from tests.unit.conftest import Compile


async def test_graph_no_proposal_ends(compiled: Compile, config: RunnableConfig) -> None:
    graph = compiled((), AIMessage("La póliza pol-1001 cubre RC y robo."))
    await graph.ainvoke({"messages": [("user", "¿qué cubre pol-1001?")]}, config)
    assert (await graph.aget_state(config)).interrupts == ()


async def test_graph_conforming_stops_then_executes(
    compiled: Compile, proposing: tuple[AIMessage, ...], config: RunnableConfig
) -> None:
    graph = compiled((True,), *proposing)
    await graph.ainvoke({"messages": [("user", "denuncia RC pol-1001")]}, config)
    stopped = await graph.aget_state(config)
    assert stopped.interrupts[0].value["propuesta"]["poliza"] == "pol-1001"
    await graph.ainvoke(Command(resume=str(Decision.APROBAR)), config)
    done = await graph.aget_state(config)
    assert done.interrupts == ()
    assert done.values["propuesta"] is None
    assert done.values["messages"][-1].text.startswith("Transacción registrada")


async def test_graph_rejected_returns_to_agent(
    compiled: Compile, proposing: tuple[AIMessage, ...], config: RunnableConfig
) -> None:
    graph = compiled((True,), *proposing, AIMessage("Entendido: la denuncia no se registra."))
    await graph.ainvoke({"messages": [("user", "denuncia RC pol-1001")]}, config)
    await graph.ainvoke(Command(resume=str(Decision.RECHAZAR)), config)
    done = await graph.aget_state(config)
    assert done.interrupts == ()
    assert done.values["messages"][-1].text == "Entendido: la denuncia no se registra."


async def test_graph_violation_feeds_back(
    compiled: Compile, proposing: tuple[AIMessage, ...], config: RunnableConfig
) -> None:
    graph = compiled((False,), *proposing, AIMessage("No procede: la fecha cae fuera de vigencia."))
    await graph.ainvoke({"messages": [("user", "denuncia RC pol-1001")]}, config)
    done = await graph.aget_state(config)
    assert done.values["intentos"] == 1
    assert done.values["errores"][0]["message"] == "fuera de vigencia"
    assert any(getattr(each, "name", "") == "validador" for each in done.values["messages"])
    assert done.values["messages"][-1].text.startswith("No procede")


@pytest.mark.parametrize(
    ("answer", "decision"),
    [("aprobar", Decision.APROBAR), ({"decision": "rechazar"}, Decision.RECHAZAR)],
    ids=["cli-value", "ui-payload"],
)
async def test_graph_decision_reads_both_drivers(answer: object, decision: Decision) -> None:
    assert ChatGraph._build_decision(answer) is decision


@pytest.mark.parametrize("answer", ["quizás", {"approved": True}, None], ids=["unknown", "foreign-shape", "none"])
async def test_graph_decision_refuses_the_rest(answer: object) -> None:
    with pytest.raises(ValueError, match=r"Decision|valid"):
        ChatGraph._build_decision(answer)


async def test_graph_execute_never_reaches_a_model() -> None:
    done = ChatGraph._build_execute(
        {"messages": [], "propuesta": {"type": "endoso", "poliza": "pol-1001", "quita": "cob-rc"}}
    )
    assert done["propuesta"] is None
    assert done["messages"][0].text.startswith("Transacción registrada (stub, sin core)")


async def test_graph_every_node_says_what_it_is(compiled: Compile) -> None:
    nodes = {node.id: node for node in LanggraphTopologyAdapter().read(compiled(())).nodes}
    declared = {name: {"label": nodes[name].label, "kind": nodes[name].kind} for name in STAGES}
    assert declared == STAGES
    assert set(AGENT_STAGES) <= set(nodes)
