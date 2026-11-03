"""models/turn: ChatTurn — what one turn leaves behind: the reply, or the stop waiting for the operator."""

from typing import Any

import msgspec


class ChatTurn(msgspec.Struct, frozen=True, kw_only=True):
    """The run and trace it was, the last thing the assistant said, and the approval request when it stopped on one."""

    run_id: str
    trace_id: str
    url: str
    reply: str = ""
    interrupt: dict[str, Any] | None = None
