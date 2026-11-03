"""models/turn: ChatTurn — what one turn leaves behind: the reply, or the stop waiting for the operator."""

from typing import Any

import msgspec
from langchain_core.runnables import RunnableConfig


class ChatRun(msgspec.Struct, frozen=True, kw_only=True):
    """One run before it starts: its ids, where its trace opens, and the config every driving side hands the graph."""

    run_id: str
    trace_id: str
    url: str
    config: RunnableConfig


class ChatTurn(msgspec.Struct, frozen=True, kw_only=True):
    """The run and trace it was, the last thing the assistant said, and the approval request when it stopped on one."""

    run_id: str
    trace_id: str
    url: str
    reply: str = ""
    interrupt: dict[str, Any] | None = None
