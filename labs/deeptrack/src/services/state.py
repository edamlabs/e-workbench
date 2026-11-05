"""services/state: the services branch — `state.services.chat` ≡ `services/chat.py`, `state.services.arms` ≡
`services/arms.py`, the business over the engines."""

from dataclasses import dataclass

from etrack.logic.viewer import Viewer

from services.arms import ArmsService
from services.chat import ChatService


@dataclass(frozen=True, slots=True)
class ServicesState:
    """The business: the configured arm's chat, the arms that build any other, and etrack's live canvas of the chat's
    graph — none without a live sink."""

    chat: ChatService
    arms: ArmsService
    viewer: Viewer | None
