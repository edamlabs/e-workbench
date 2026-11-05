# e-track

Run tracking for agent systems. A source turns a framework's run into **one event model**; the model travels on a
**structlog channel** of its own; a bus fans it out to **parallel sinks**, each reading the partial view it declares.

```
framework hooks ─► source ─► fold ─► channel (validate → publish → forward to host logger)
                                                 │
                                                 └─► bus ─┬─► otlp   spans + logs → Langfuse · LangSmith · Tempo · Phoenix
                                                          ├─► live   per-thread replay + push → a canvas, a chat
                                                          └─► yours  any SinkPort, any EventView
```

##### INSTALL #####

Not published yet: depend on it by path.

```toml
[project]
dependencies = ["e-track[langgraph,otel,topology]"]

[tool.uv.sources]
e-track = { path = "../etrack", editable = true }
```

Extras: `langgraph` (LangGraph/deepagents source and topology), `otel` (OTLP driver), `topology` (layout).

##### USAGE #####

```python
from contextlib import AsyncExitStack

from etrack.logic.api import Tracker
from etrack.logic.channel import EventChannel
from etrack.models.event import EventKind
from etrack.providers.adapters.bus.anyio import AnyioBusAdapter
from etrack.providers.adapters.sink.live import LiveSinkAdapter
from etrack.providers.adapters.source.langgraph import LanggraphSourceAdapter
from etrack.providers.drivers.sink.otlp import OtlpDriver

async with AsyncExitStack() as stack:                       # the host's composition root
    live = await stack.enter_async_context(LiveSinkAdapter())
    otlp = await stack.enter_async_context(OtlpDriver())
    bus = AnyioBusAdapter()
    bus.subscribe(live)
    bus.subscribe(otlp, select=lambda event: event if event.part is None else None)  # policy per sink
    await stack.enter_async_context(bus)                   # opened last: closed first, drains into the sinks
    tracker = Tracker(EventChannel(bus), LanggraphSourceAdapter(mcp=frozenset({"onto_query"})))

    with tracker.track(thread="t1", config={"configurable": {"thread_id": "t1"}}) as run:
        await graph.ainvoke({"messages": [("user", "hola")]}, run.config)
        with run.fold.span("gate", kind=EventKind.EVALUATION):
            ...                                             # the project's own code, same tree
```

With the house renderer (`ELogger`) on the host:

```
2026-11-03T12:00:00Z | INFO | run.event || run_id: 019a… || kind: node || phase: start || name: agent || step: 1
```

Every frame is also a line on the host's `etrack` logger, rendered by the host's own structlog setup; e-track never
configures logging.

##### THE RECORD #####

| Field | What |
|---|---|
| `run_id`, `thread_id` | the run (32 hex, also the W3C trace id) and the conversation |
| `seq`, `id`, `parent` | order within the run; the span and its visible parent |
| `kind` | `run agent subagent node llm embedding retrieval tool mcp interrupt state evaluation custom` |
| `phase` | `start delta end error instant` |
| `part` | on deltas: `text reasoning tool_call image audio video file custom` |
| `node`, `ns`, `step`, `visit` | graph coordinates: node, subgraph path, superstep, times the run entered the node |
| `message_id`, `call_id` | the chat message and the tool call a client renders |
| `model`, `usage`, `error` | typed sections: provider/name/params, tokens/cost, failure |
| `payload`, `attributes` | what the span carried (redacted); the open, namespaced extension bag |

Grow it by subclassing `RunEvent` and passing the subclass to `EventChannel(model=…)`; read it through an `EventView`.

##### GATES #####

```bash
make install      # sync deps + git hooks
make check        # lint + type + arch + validate + test
make cov          # coverage gate: 100 % lines and branches, every outbound service faked in process
make e2e          # sandbox up (compose: one OTel Collector, OTLP/HTTP :28120), then the end-to-end tier
make down         # sandbox down, its output dropped
make test TESTARGS="-m slow"   # the producer's cost per emission
```
