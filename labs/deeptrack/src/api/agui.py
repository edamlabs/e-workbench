"""api/agui: `POST /agui` — the AG-UI driving side: CopilotKit's runtime streams a run of the outer graph from here.

One AG-UI agent per request, built over the run's config: etrack's source rides every request, the run tracked for as
long as its stream lasts, and the thread id the client sends is the conversation. The adapter (`ag-ui-langgraph`) owns
the protocol — messages, tool calls, interrupts and their resume."""

from collections.abc import AsyncIterator

from ag_ui.core import RunAgentInput
from ag_ui.encoder import EventEncoder
from ag_ui_langgraph import LangGraphAgent
from litestar import Request, post
from litestar.params import JSONBody
from litestar.response import Stream

from services.chat import ChatService
from services.state import ServicesState


class RunAgui:
    """One AG-UI run as an async iterable of encoded events — the run tracked for exactly as long as it is iterated."""

    __slots__ = ("_chat", "_data", "_encoder")

    def __init__(self, chat: ChatService, data: RunAgentInput, encoder: EventEncoder) -> None:
        self._chat = chat
        self._data = data
        self._encoder = encoder

    ############################################################

    async def __aiter__(self) -> AsyncIterator[str]:
        """The encoded events of the outer graph on the client's thread."""
        with self._chat.run(self._data.thread_id) as run:
            agent = LangGraphAgent(name="deeptrack", graph=self._chat.graph, config=run.config)
            async for event in agent.run(self._data):
                yield self._encoder.encode(event)


@post("/agui")
async def agui(data: JSONBody[RunAgentInput], request: Request) -> Stream:
    """One AG-UI run: the encoded event stream of the outer graph on the client's thread."""
    services: ServicesState = request.app.state.deeptrack.services
    encoder = EventEncoder(accept=request.headers.get("accept", "text/event-stream"))
    return Stream(RunAgui(services.chat, data, encoder), media_type=encoder.get_content_type())
