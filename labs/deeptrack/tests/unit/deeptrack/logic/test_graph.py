"""The outer graph's routes, driven by a scripted model: no proposal, approve, reject, violation."""

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from deeptrack.models.proposal import Decision

CONFIG: RunnableConfig = {"configurable": {"thread_id": "t"}, "recursion_limit": 80}


async def test_graph_no_proposal_ends(compiled) -> None:
    graph = compiled((), AIMessage("La póliza pol-1001 cubre RC y robo."))
    await graph.ainvoke({"messages": [("user", "¿qué cubre pol-1001?")]}, CONFIG)
    assert (await graph.aget_state(CONFIG)).interrupts == ()


async def test_graph_conforming_stops_then_executes(compiled, proposing) -> None:
    graph = compiled((True,), *proposing)
    await graph.ainvoke({"messages": [("user", "denuncia RC pol-1001")]}, CONFIG)
    stopped = await graph.aget_state(CONFIG)
    assert stopped.interrupts[0].value["propuesta"]["poliza"] == "pol-1001"
    await graph.ainvoke(Command(resume=str(Decision.APROBAR)), CONFIG)
    done = await graph.aget_state(CONFIG)
    assert done.interrupts == ()
    assert done.values["propuesta"] is None
    assert done.values["messages"][-1].text.startswith("Transacción registrada")


async def test_graph_rejected_returns_to_agent(compiled, proposing) -> None:
    graph = compiled((True,), *proposing, AIMessage("Entendido: la denuncia no se registra."))
    await graph.ainvoke({"messages": [("user", "denuncia RC pol-1001")]}, CONFIG)
    await graph.ainvoke(Command(resume=str(Decision.RECHAZAR)), CONFIG)
    done = await graph.aget_state(CONFIG)
    assert done.interrupts == ()
    assert done.values["messages"][-1].text == "Entendido: la denuncia no se registra."


async def test_graph_violation_feeds_back(compiled, proposing) -> None:
    graph = compiled((False,), *proposing, AIMessage("No procede: la fecha cae fuera de vigencia."))
    await graph.ainvoke({"messages": [("user", "denuncia RC pol-1001")]}, CONFIG)
    done = await graph.aget_state(CONFIG)
    assert done.values["intentos"] == 1
    assert done.values["errores"][0]["message"] == "fuera de vigencia"
    assert any(getattr(each, "name", "") == "validador" for each in done.values["messages"])
    assert done.values["messages"][-1].text.startswith("No procede")
