# e-track

The record, the channel, the bus and the providers, one section each. The README holds the overview and the install.

## `Tracker.track`

```python
with tracker.track("t1", config) as run:      # run.scope.run_id == LangChain's root run id
    await graph.ainvoke(inputs, run.config)
```

| kwarg | type | default | |
|---|---|---|---|
| `thread` | `str` | — | the conversation; every frame carries it |
| `config` | the source's config (`RunnableConfig`) | — | returned with the source's hook bound |
| `run_id` | `str \| None` | uuid7 hex | pin a run id the host already chose |

## `EventChannel`

```python
channel.emit(event)                                        # a record already built
channel.log.info("run.event", run_id=…, seq=…, id=…, kind="custom", phase="instant")   # reserved keys
```

| kwarg | type | default | |
|---|---|---|---|
| `bus` | `BusPort` | — | where validated records go |
| `model` | `type[RunEvent]` | `RunEvent` | a project's subclass to validate into |
| `forward` | `type[EventView] \| None` | `LogView` | what reaches the host's `etrack` logger; `None`: nothing |

## `AnyioBusAdapter`

```python
bus.subscribe(sink, select=lambda event: None if event.part is Part.REASONING else event)
```

`publish` never waits: a full sink drops (`bus.dropped`), a raising sink is skipped (`bus.failed`). Setting:
`ETRACK_BUS_CAPACITY` (1000). A synchronous burst longer than the capacity, with no await in between, drops the rest.

## `LanggraphSourceAdapter`

| kwarg | type | default | |
|---|---|---|---|
| `mcp` | `frozenset[str]` | `∅` | tool names that are MCP calls |
| `subagents` | `frozenset[str]` | `{"task"}` | tools that delegate to a subagent (named by `subagent_type`) |

| LangChain sees | frame |
|---|---|
| root chain | `run` |
| chain named after its `langgraph_node` | `node` (one span for a mounted subgraph) |
| chat model / LLM | `llm` + deltas typed by v1 content block |
| tool · MCP tool · `task` | `tool` · `mcp` · `subagent` |
| retriever | `retrieval` |
| `GraphInterrupt` | `interrupt` instant, once, under the span that raised |
| `dispatch_custom_event` | `custom` instant |

## `LiveSinkAdapter`

```python
async for frame in live.watch("t1", after=last_offset):   # replay, then follow
    send(frame.offset, frame.event)
```

Settings: `ETRACK_LIVE_BUFFER` (2000 per thread), `ETRACK_LIVE_THREADS` (256), `ETRACK_LIVE_BACKLOG` (1000).

## `OtlpDriver`

| Setting | default | |
|---|---|---|
| `ETRACK_OTLP_TARGETS` | `{}` | `{"name": {"endpoint": base, "headers": {…}}}` — `/v1/traces`, `/v1/logs` appended |
| `ETRACK_OTLP_TRACES` / `_LOGS` | `true` / `false` | which signals leave |
| `ETRACK_OTLP_FLUSH` / `_TIMEOUT` | `1s` / `10s` | batch cadence, export deadline |
| `ETRACK_OTLP_SERVICE` | `etrack` | `service.name` |

Trace id = run id; span id = the frame id's low 64 bits. `driver.processor()` is a structlog processor the host may add
to its own chain so its application logs leave as OTel records too.

## `LayoutProcessor`

```python
placed = LayoutProcessor().place(LanggraphTopologyAdapter().read(graph))   # rank, lane, loop
```
