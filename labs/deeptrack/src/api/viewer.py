"""api/viewer: `/etrack/` — etrack's live canvas mounted beside the chat, on the same server and port.

The canvas is built in the lifespan (it needs the compiled graph); this mount reaches it in the tree at request time and
hands it the request whole, prefix stripped. Without a live sink there is no canvas: the mount answers 503."""

from litestar import asgi
from litestar.exceptions import ServiceUnavailableException
from litestar.types import Receive, Scope, Send

from services.state import ServicesState


@asgi("/etrack", is_mount=True, copy_scope=True)
async def viewer(scope: Scope, receive: Receive, send: Send) -> None:
    """etrack's viewer app: the declared graph, every thread the live sink keeps, a thread live over SSE."""
    services: ServicesState = scope["app"].state.deeptrack.services
    match services.viewer:
        case None:
            msg = "no live sink is subscribed: add `live` to DEEPTRACK_TRACK_SINKS"
            raise ServiceUnavailableException(msg)
        case canvas:
            await canvas.app(scope, receive, send)
