"""tests/unit/etrack/providers/adapters/source/langgraph: real LangGraph runs — plain, deep agent, subgraph, interrupt."""

import uuid
from typing import Any

import pytest
from deepagents import create_deep_agent
from langchain_core.callbacks import AsyncCallbackManager, BaseCallbackHandler
from langchain_core.callbacks.manager import adispatch_custom_event
from langchain_core.documents import Document
from langchain_core.language_models.fake import FakeListLLM
from langchain_core.messages import AIMessage
from langchain_core.retrievers import BaseRetriever

### LangGraph reads a node's `config: RunnableConfig` annotation at runtime to decide what to pass it.
from langchain_core.runnables import RunnableConfig  # noqa: TC002
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import ParentCommand
from langgraph.graph import END, START, MessagesState
from langgraph.types import Command, interrupt

from etrack.infra.errors import SourceError
from etrack.models.event import EventKind, EventPhase, Failure, Part, RunEvent, RunScope, Usage
from etrack.ports.source import SourcePort
from etrack.processors.fold import FoldProcessor
from etrack.providers.adapters.source.langgraph import LanggraphHandler, LanggraphSourceAdapter
from support.graph import state_graph
from support.model import ScriptedModel, call, script, think
from unit.etrack.conftest import RUN

SCOPE = RunScope(run_id=RUN, thread_id="t1")


##### HELPERS #####
def bound(
    source: LanggraphSourceAdapter, config: RunnableConfig | None = None
) -> tuple[list[RunEvent], RunnableConfig]:
    emitted: list[RunEvent] = []
    fold = FoldProcessor(SCOPE, emitted.append)
    return emitted, source.bind(fold, SCOPE, config or {})


def agent_graph(model: ScriptedModel) -> Any:
    async def agent(state: MessagesState) -> dict[str, Any]:
        return {"messages": [await model.ainvoke(state["messages"])]}

    graph = state_graph(MessagesState)
    graph.add_node("agent", agent)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", END)
    return graph.compile()


def lineage(spans: dict[str, RunEvent], span: str) -> list[EventKind]:
    """The kinds from a span up to the root."""
    return [spans[span].kind, *lineage(spans, spans[span].parent)] if span else []


def kinds(emitted: list[RunEvent], phase: EventPhase = EventPhase.START) -> list[tuple[EventKind, str]]:
    return [(event.kind, event.name) for event in emitted if event.phase is phase]


def by(emitted: list[RunEvent], kind: EventKind, phase: EventPhase) -> list[RunEvent]:
    return [event for event in emitted if event.kind is kind and event.phase is phase]


##### LIFECYCLE #####
async def test_langgraph_meets_port() -> None:
    async with LanggraphSourceAdapter() as source:
        assert isinstance(source, SourcePort)
        assert await source.health()


async def test_langgraph_hex_none() -> None:
    assert LanggraphHandler._common_hex(None) == ""


##### BIND #####
@pytest.mark.parametrize(
    ("callbacks", "count"),
    [(None, 1), ([BaseCallbackHandler()], 2)],
    ids=["none", "list"],
)
async def test_langgraph_bind_callbacks(callbacks: list[Any] | None, count: int) -> None:
    _, config = bound(LanggraphSourceAdapter(), {"callbacks": callbacks, "metadata": {"app": "x"}})
    assert len(config["callbacks"]) == count  # ty: ignore[invalid-argument-type]
    assert isinstance(config["callbacks"][-1], LanggraphHandler)  # ty: ignore[not-subscriptable]
    assert config.get("run_id") == uuid.UUID(RUN)
    assert config["metadata"] == {"app": "x", "etrack_run_id": RUN, "etrack_thread_id": "t1"}


async def test_langgraph_bind_manager_kept() -> None:
    inherited = BaseCallbackHandler()
    manager = AsyncCallbackManager(handlers=[inherited])
    _, config = bound(LanggraphSourceAdapter(), {"callbacks": manager})
    bound_manager = config["callbacks"]
    assert isinstance(bound_manager, AsyncCallbackManager)
    assert inherited in bound_manager.handlers
    assert any(isinstance(handler, LanggraphHandler) for handler in bound_manager.handlers)
    assert len(manager.handlers) == 1  # the host's manager is untouched


async def test_langgraph_bind_rejects() -> None:
    with pytest.raises(SourceError, match="list or a manager"):
        bound(LanggraphSourceAdapter(), {"callbacks": "nope"})  # ty: ignore[invalid-argument-type]


##### PLAIN GRAPH #####
async def test_langgraph_plain_run() -> None:
    emitted, config = bound(LanggraphSourceAdapter())
    await agent_graph(script("hola mundo")).ainvoke({"messages": [("user", "hi")]}, config)
    assert kinds(emitted) == [(EventKind.RUN, "LangGraph"), (EventKind.NODE, "agent"), (EventKind.LLM, "ScriptedModel")]
    assert emitted[0].id == RUN
    node = by(emitted, EventKind.NODE, EventPhase.START)[0]
    assert (node.parent, node.step, node.visit, node.node) == (RUN, 1, 1, "agent")
    llm = by(emitted, EventKind.LLM, EventPhase.END)[0]
    assert (llm.parent, llm.payload["text"]) == (node.id, "hola mundo")
    assert [event.seq for event in emitted] == list(range(len(emitted)))


async def test_langgraph_text_deltas() -> None:
    emitted, config = bound(LanggraphSourceAdapter())
    await agent_graph(script("hola mundo")).ainvoke({"messages": [("user", "hi")]}, config, stream_mode="messages")
    deltas = by(emitted, EventKind.LLM, EventPhase.DELTA)
    assert [(event.part, event.payload["delta"]) for event in deltas] == [(Part.TEXT, "hola mundo")]
    assert deltas[0].message_id == deltas[0].id


async def test_langgraph_reasoning_and_usage() -> None:
    emitted, config = bound(LanggraphSourceAdapter())
    turn = think("primero pienso", "luego digo", input_tokens=3, output_tokens=5, total_tokens=8)
    await agent_graph(script(turn)).ainvoke({"messages": [("user", "hi")]}, config, stream_mode="messages")
    deltas = by(emitted, EventKind.LLM, EventPhase.DELTA)
    assert [(event.part, event.payload["delta"]) for event in deltas] == [
        (Part.REASONING, "primero pienso"),
        (Part.TEXT, "luego digo"),
    ]
    end = by(emitted, EventKind.LLM, EventPhase.END)[0]
    assert (end.payload["text"], end.payload["reasoning"]) == ("luego digo", "primero pienso")
    assert end.usage == Usage(input_tokens=3, output_tokens=5, total_tokens=8)


async def test_langgraph_model_ref() -> None:
    emitted, config = bound(LanggraphSourceAdapter())
    await agent_graph(script("ok")).ainvoke({"messages": [("user", "hi")]}, config)
    start = by(emitted, EventKind.LLM, EventPhase.START)[0]
    assert start.model is not None
    assert start.model.name == "ScriptedModel"
    assert start.payload["input"] == [{"role": "human", "content": "hi"}]


async def test_langgraph_node_error() -> None:
    def broken(state: MessagesState) -> dict[str, Any]:
        msg = "bad input"
        raise ValueError(msg)

    graph = state_graph(MessagesState)
    graph.add_node("broken", broken)
    graph.add_edge(START, "broken")
    emitted, config = bound(LanggraphSourceAdapter())
    with pytest.raises(ValueError, match="bad input"):
        await graph.compile().ainvoke({"messages": []}, config)
    failed = [event for event in emitted if event.phase is EventPhase.ERROR]
    assert [event.kind for event in failed] == [EventKind.NODE, EventKind.RUN]
    assert failed[0].error == Failure(type="ValueError", message="bad input")


async def test_langgraph_loop_visits() -> None:
    def tick(state: dict[str, int]) -> dict[str, int]:
        return {"n": state["n"] + 1}

    def route(state: dict[str, int]) -> str:
        return "tick" if state["n"] < 3 else END

    graph = state_graph(dict)
    graph.add_node("tick", tick)
    graph.add_edge(START, "tick")
    graph.add_conditional_edges("tick", route, ["tick", END])
    emitted, config = bound(LanggraphSourceAdapter())
    await graph.compile().ainvoke({"n": 0}, config)
    starts = by(emitted, EventKind.NODE, EventPhase.START)
    assert [(event.visit, event.step) for event in starts] == [(1, 1), (2, 2), (3, 3)]


async def test_langgraph_subgraph_one_span() -> None:
    inner = agent_graph(script("dentro"))
    outer = state_graph(MessagesState)
    outer.add_node("agent", inner)
    outer.add_edge(START, "agent")
    emitted, config = bound(LanggraphSourceAdapter())
    await outer.compile().ainvoke({"messages": [("user", "hi")]}, config)
    nodes = by(emitted, EventKind.NODE, EventPhase.START)
    ### the mounted subgraph and its own `agent` node: two spans, not three.
    assert [event.name for event in nodes] == ["agent", "agent"]
    assert nodes[1].parent == nodes[0].id


##### INTERRUPT #####
async def test_langgraph_interrupt_and_resume() -> None:
    def ask(state: MessagesState) -> dict[str, Any]:
        answer = interrupt({"q": "¿apruebas?"})
        return {"messages": [("ai", f"dijiste {answer}")]}

    graph = state_graph(MessagesState)
    graph.add_node("ask", ask)
    graph.add_edge(START, "ask")
    compiled = graph.compile(checkpointer=InMemorySaver())
    thread: RunnableConfig = {"configurable": {"thread_id": "t1"}}
    emitted, config = bound(LanggraphSourceAdapter(), thread)
    await compiled.ainvoke({"messages": []}, config)
    (stop,) = [event for event in emitted if event.kind is EventKind.INTERRUPT]
    node = by(emitted, EventKind.NODE, EventPhase.START)[0]
    assert (stop.phase, stop.parent, stop.payload) == (EventPhase.INSTANT, node.id, {"value": [{"q": "¿apruebas?"}]})
    assert by(emitted, EventKind.NODE, EventPhase.END)[0].payload == {"interrupted": True}
    resumed, config = bound(LanggraphSourceAdapter(), thread)
    await compiled.ainvoke(Command(resume="sí"), config)
    assert [event.kind for event in resumed if event.kind is EventKind.INTERRUPT] == []
    assert by(resumed, EventKind.NODE, EventPhase.END)


async def test_langgraph_nested_interrupt_once() -> None:
    def ask(state: MessagesState) -> dict[str, Any]:
        interrupt({"q": "?"})
        return {}

    inner = state_graph(MessagesState)
    inner.add_node("ask", ask)
    inner.add_edge(START, "ask")
    outer = state_graph(MessagesState)
    outer.add_node("sub", inner.compile())
    outer.add_edge(START, "sub")
    emitted, config = bound(LanggraphSourceAdapter(), {"configurable": {"thread_id": "t1"}})
    await outer.compile(checkpointer=InMemorySaver()).ainvoke({"messages": []}, config)
    (stop,) = [event for event in emitted if event.kind is EventKind.INTERRUPT]
    ask_span = next(event for event in emitted if event.name == "ask" and event.phase is EventPhase.START)
    assert stop.parent == ask_span.id


##### FAILURES #####
async def test_langgraph_llm_error() -> None:
    class Down(ScriptedModel):
        def _generate(self, *args: Any, **kwargs: Any) -> Any:
            msg = "quota"
            raise RuntimeError(msg)

    emitted, config = bound(LanggraphSourceAdapter())
    with pytest.raises(RuntimeError, match="quota"):
        await Down(messages=iter([])).ainvoke("hi", config)
    (failed,) = [event for event in emitted if event.phase is EventPhase.ERROR]
    assert (failed.kind, failed.error) == (EventKind.LLM, Failure(type="RuntimeError", message="quota"))


async def test_langgraph_retriever_error() -> None:
    class Down(BaseRetriever):
        def _get_relevant_documents(self, query: str, *, run_manager: Any) -> list[Document]:
            msg = "index gone"
            raise LookupError(msg)

    emitted, config = bound(LanggraphSourceAdapter())
    with pytest.raises(LookupError, match="index gone"):
        await Down().ainvoke("q", config)
    (failed,) = [event for event in emitted if event.phase is EventPhase.ERROR]
    assert (failed.kind, failed.error) == (EventKind.RETRIEVAL, Failure(type="LookupError", message="index gone"))


##### TOOLS, RETRIEVERS, CUSTOM #####
async def test_langgraph_deep_agent_subagent_and_mcp() -> None:
    @tool
    def onto_query(query: str) -> str:
        """Run a SPARQL query."""
        return "seg:Poliza"

    model = script(
        call("task", "c1", subagent_type="ontologo", description="resuelve Poliza"),
        call("onto_query", "c2", query="SELECT *"),
        "Poliza es seg:Poliza",
        "listo",
    )
    agent = create_deep_agent(
        model=model,
        subagents=[
            {"name": "ontologo", "description": "ontología", "system_prompt": "eres el ontólogo", "tools": [onto_query]}
        ],
    )
    emitted, config = bound(LanggraphSourceAdapter(mcp=frozenset({"onto_query"})))
    await agent.ainvoke({"messages": [("user", "¿qué es una póliza?")]}, config, stream_mode="messages")
    (subagent,) = by(emitted, EventKind.SUBAGENT, EventPhase.START)
    (mcp,) = by(emitted, EventKind.MCP, EventPhase.START)
    assert (subagent.name, subagent.call_id) == ("ontologo", "c1")
    assert mcp.name == "onto_query"
    spans = {event.id: event for event in emitted if event.phase is EventPhase.START}
    assert EventKind.SUBAGENT in lineage(spans, mcp.parent)
    assert by(emitted, EventKind.MCP, EventPhase.END)[0].payload == {"output": "seg:Poliza"}
    calls = [event for event in emitted if event.part is Part.TOOL_CALL]
    assert {event.call_id for event in calls} == {"c1", "c2"}
    ends = by(emitted, EventKind.LLM, EventPhase.END)
    assert [call["id"] for end in ends for call in end.payload["tool_calls"]] == ["c1", "c2"]


async def test_langgraph_parallel_tools() -> None:
    @tool
    def poliza(name: str) -> str:
        """Read a policy."""
        return name

    both = AIMessage(
        "",
        tool_calls=[
            {"name": "poliza", "args": {"name": "pol-1"}, "id": "c1", "type": "tool_call"},
            {"name": "poliza", "args": {"name": "pol-2"}, "id": "c2", "type": "tool_call"},
        ],
    )
    agent = create_deep_agent(model=script(both, "dos pólizas"), tools=[poliza])
    emitted, config = bound(LanggraphSourceAdapter())
    await agent.ainvoke({"messages": [("user", "hi")]}, config)
    starts = by(emitted, EventKind.TOOL, EventPhase.START)
    ends = by(emitted, EventKind.TOOL, EventPhase.END)
    assert sorted(event.call_id for event in starts) == ["c1", "c2"]
    ### LangGraph sends each call to its own `tools` task: two node spans of one superstep, one tool under each.
    nodes = {event.id: event for event in by(emitted, EventKind.NODE, EventPhase.START)}
    parents = [nodes[event.parent] for event in starts]
    assert {(node.name, node.step) for node in parents} == {("tools", parents[0].step)}
    assert len({node.id for node in parents}) == 2
    assert sorted(event.payload["output"] for event in ends) == ["pol-1", "pol-2"]


async def test_langgraph_tool_error() -> None:
    @tool
    def falla(x: int) -> str:
        """Always fails."""
        msg = "no"
        raise RuntimeError(msg)

    agent = create_deep_agent(model=script(call("falla", "c1", x=1), "vale"), tools=[falla])
    emitted, config = bound(LanggraphSourceAdapter())
    with pytest.raises(RuntimeError, match="no"):
        await agent.ainvoke({"messages": [("user", "hi")]}, config)
    (failed,) = [event for event in emitted if event.kind is EventKind.TOOL and event.phase is EventPhase.ERROR]
    assert failed.error == Failure(type="RuntimeError", message="no")


async def test_langgraph_retriever() -> None:
    class Fixed(BaseRetriever):
        def _get_relevant_documents(self, query: str, *, run_manager: Any) -> list[Document]:
            return [Document(page_content="póliza", metadata={"id": 1})]

    async def search(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
        await Fixed().ainvoke("póliza", config)
        return {}

    graph = state_graph(MessagesState)
    graph.add_node("search", search)
    graph.add_edge(START, "search")
    emitted, config = bound(LanggraphSourceAdapter())
    await graph.compile().ainvoke({"messages": []}, config)
    (start,) = by(emitted, EventKind.RETRIEVAL, EventPhase.START)
    (end,) = by(emitted, EventKind.RETRIEVAL, EventPhase.END)
    assert (start.name, start.payload) == ("Fixed", {"query": "póliza"})
    assert end.payload == {"documents": [{"content": "póliza", "metadata": {"id": 1}}]}


async def test_langgraph_custom_event() -> None:
    async def gate(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
        await adispatch_custom_event("verdict", {"conforms": False}, config=config)
        return {}

    graph = state_graph(MessagesState)
    graph.add_node("gate", gate)
    graph.add_edge(START, "gate")
    emitted, config = bound(LanggraphSourceAdapter())
    await graph.compile().ainvoke({"messages": []}, config)
    (custom,) = [event for event in emitted if event.kind is EventKind.CUSTOM]
    node = by(emitted, EventKind.NODE, EventPhase.START)[0]
    assert (custom.phase, custom.name, custom.parent, custom.payload) == (
        EventPhase.INSTANT,
        "verdict",
        node.id,
        {"data": {"conforms": False}},
    )


async def test_langgraph_plain_llm() -> None:
    emitted, config = bound(LanggraphSourceAdapter())
    await FakeListLLM(responses=["texto"]).ainvoke("prompt", config)
    assert kinds(emitted) == [(EventKind.LLM, "FakeListLLM")]
    assert by(emitted, EventKind.LLM, EventPhase.END)[0].payload["text"] == "texto"
    assert by(emitted, EventKind.LLM, EventPhase.START)[0].payload == {"input": ["prompt"]}


async def test_langgraph_sync_invoke() -> None:
    emitted, config = bound(LanggraphSourceAdapter())
    model = script("sincrono")

    def agent(state: MessagesState) -> dict[str, Any]:
        return {"messages": [model.invoke(state["messages"])]}

    graph = state_graph(MessagesState)
    graph.add_node("agent", agent)
    graph.add_edge(START, "agent")
    graph.compile().invoke({"messages": [("user", "hi")]}, config)
    assert kinds(emitted) == [(EventKind.RUN, "LangGraph"), (EventKind.NODE, "agent"), (EventKind.LLM, "ScriptedModel")]


##### PIECES #####
@pytest.mark.parametrize(
    ("block", "expected"),
    [
        ({"type": "text", "text": "a"}, (Part.TEXT, {"delta": "a"}, "")),
        ({"type": "text", "text": ""}, None),
        ({"type": "reasoning", "reasoning": "r"}, (Part.REASONING, {"delta": "r"}, "")),
        (
            {"type": "tool_call_chunk", "args": "{", "name": "t", "id": "c"},
            (Part.TOOL_CALL, {"delta": "{", "name": "t"}, "c"),
        ),
        ({"type": "tool_call", "args": {}, "id": "c"}, (Part.TOOL_CALL, {"delta": {}}, "c")),
        ({"type": "image", "url": "u"}, (Part.IMAGE, {"block": {"type": "image", "url": "u"}}, "")),
        ({"type": "weird"}, (Part.CUSTOM, {"block": {"type": "weird"}}, "")),
    ],
    ids=["text", "empty", "reasoning", "chunk", "call", "image", "custom"],
)
async def test_langgraph_piece(block: dict[str, Any], expected: Any) -> None:
    assert LanggraphHandler._llm_piece(block) == expected


@pytest.mark.parametrize(
    ("token", "blocks"),
    [
        ("a", [{"type": "text", "text": "a"}]),
        (
            ["a", {"type": "reasoning", "reasoning": "r"}],
            [{"type": "text", "text": "a"}, {"type": "reasoning", "reasoning": "r"}],
        ),
    ],
    ids=["str", "parts"],
)
async def test_langgraph_token(token: Any, blocks: list[dict[str, Any]]) -> None:
    assert LanggraphHandler._llm_token(token) == blocks


async def test_langgraph_usage_absent() -> None:
    assert LanggraphHandler._llm_usage(object()) is None


async def test_langgraph_bubble_up_not_failure() -> None:
    emitted: list[RunEvent] = []
    fold = FoldProcessor(SCOPE, emitted.append)
    handler = LanggraphHandler(fold, frozenset(), frozenset())
    run = uuid.UUID(RUN)
    handler.on_chain_start({}, {}, run_id=run, name="root")
    handler.on_chain_error(ParentCommand(Command(goto="x")), run_id=run)
    assert (emitted[-1].phase, emitted[-1].payload) == (EventPhase.END, {"bubbled": "ParentCommand"})
