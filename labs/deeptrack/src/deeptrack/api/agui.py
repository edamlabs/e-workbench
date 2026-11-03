"""api/agui: `POST /agui` — the AG-UI driving side: CopilotKit's runtime streams a run of the outer graph from here.

One AG-UI agent per request, built over the run's config: the projector (frames to the server's console) and the
tracer's handler ride every request, and the thread id the client sends is the conversation. The adapter
(`ag-ui-langgraph`) owns the protocol — messages, tool calls, interrupts and their resume."""

from collections.abc import AsyncIterator

from ag_ui.core import RunAgentInput
from ag_ui.encoder import EventEncoder
from ag_ui_langgraph import LangGraphAgent
from litestar import Request, post
from litestar.response import Stream

from deeptrack.cli.console import EventConsole
from deeptrack.state import ServicesState

CONSOLE = EventConsole()


async def _agui_stream(agent: LangGraphAgent, data: RunAgentInput, encoder: EventEncoder) -> AsyncIterator[str]:
    async for event in agent.run(data):
        yield encoder.encode(event)


@post("/agui")
async def agui(data: RunAgentInput, request: Request) -> Stream:
    """One AG-UI run: the encoded event stream of the outer graph on the client's thread."""
    services: ServicesState = request.app.state.deeptrack.services
    run, _ = services.chat.run(data.thread_id, CONSOLE.show)
    agent = LangGraphAgent(name="deeptrack", graph=services.chat.graph, config=run.config)
    encoder = EventEncoder(accept=request.headers.get("accept", "text/event-stream"))
    return Stream(_agui_stream(agent, data, encoder), media_type=encoder.get_content_type())
