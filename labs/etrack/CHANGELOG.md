# Changelog

All notable changes to e-track are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- `RunEvent` v1: one record per span edge — `kind` (13, `CUSTOM` fallback) × `phase` (start, delta, end, error,
  instant) × `part` (text, reasoning, tool call, media, custom); typed `model`/`usage`/`error` sections, an open
  `attributes` bag, subclassable; `EventView` narrows it per client.
- `EventChannel`: the log as the bus — reserved keys validated, published, forwarded to the host's `etrack` logger.
- `Tracker.track`: one run from a host config — uuid7 run id pinned as LangChain's root, contextvars bound.
- `FoldProcessor`: edges → ordered, parented frames (`seq`, `visit`, latency, redaction, own spans and instants).
- Providers: `AnyioBusAdapter` (bounded per-sink fan-out, thread-safe publish, drop and failure counters),
  `LanggraphSourceAdapter` (callbacks inline: run, node, LLM, tool, MCP, subagent, retriever, interrupt, custom; v1
  content blocks), `LanggraphTopologyAdapter`, `LiveSinkAdapter` (per-thread replay by offset), `OtlpDriver` (spans and
  logs with derived W3C ids; GenAI, OpenInference and Langfuse attributes; host log processor).
- `LayoutProcessor`: ranks, lanes and loops of a declared graph (rustworkx).
- Sandbox: `compose.yml` with one OpenTelemetry Collector writing OTLP/JSON to `.sandbox/`; `make stack · e2e · down`.
  The end-to-end tier runs a deep agent (subagent + MCP tool) through every layer into it.

### Fixed

- The OTLP driver encodes attribute values with e-serde: pydantic messages, dataclass commands, structs and dates
  canonicalized, unknown objects as text. Found by the e2e run: a `ToolMessage` output made the OTLP sink fail.
  Serialization is each sink's own concern; the record carries what the source saw.
