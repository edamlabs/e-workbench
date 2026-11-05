"""api/viewer: etrack's canvas mounted at /etrack — its API reached through the mount, 503 without a live sink."""

from etrack.logic.viewer import Viewer
from etrack.models.event import EventKind, EventPhase, RunEvent
from etrack.ports.topology import Topology
from etrack.providers.adapters.sink.live import LiveAdapter
from litestar.testing import AsyncTestClient

from tests.unit.api.conftest import ViewerOver


async def test_viewer_mount_reaches_the_canvas_api(viewer_over: ViewerOver, topology: Topology) -> None:
    live = LiveAdapter()
    await live.send(RunEvent(run_id="r", thread_id="t1", seq=0, id="s", kind=EventKind.RUN, phase=EventPhase.START))
    async with AsyncTestClient(viewer_over(Viewer(watch=live, topology=topology))) as client:
        shown = (await client.get("/etrack/api/topology")).json()
        threads = (await client.get("/etrack/api/threads")).json()
    assert [node["id"] for node in shown["nodes"]] == ["agent"]
    assert [thread["thread"] for thread in threads] == ["t1"]


async def test_viewer_mount_without_live_sink(viewer_over: ViewerOver) -> None:
    async with AsyncTestClient(viewer_over(None)) as client:
        reply = await client.get("/etrack/api/topology")
    assert reply.status_code == 503
