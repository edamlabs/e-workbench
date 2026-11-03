"""logic.state: ChatState — the outer graph's state, the deep agent's own schema widened by what the gate decides on.

Decision data only: the pending `propuesta` (it must survive the approval interrupt), the last `errores` the gate
found, and the `intentos` counted against the retry cap. Nothing a UI merely shows lives here — that is a frame."""

from typing import Any, NotRequired

from deepagents.graph import DeepAgentState


class ChatState(DeepAgentState):
    """Messages (the deep agent's delta channel), the pending proposal, the gate's last report, the retries spent."""

    propuesta: NotRequired[dict[str, Any] | None]
    errores: NotRequired[list[dict[str, Any]]]
    intentos: NotRequired[int]
