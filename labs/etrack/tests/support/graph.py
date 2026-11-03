"""tests/support/graph: a LangGraph StateGraph over any state schema, the one place its typing gap is acknowledged."""

from typing import Any

from langgraph.graph import StateGraph


def state_graph(schema: Any) -> StateGraph[Any]:
    """A new StateGraph over `schema`.

    ### ty cannot prove a TypedDict (MessagesState) meets StateGraph's bound; LangGraph accepts it at runtime."""
    return StateGraph(schema)
