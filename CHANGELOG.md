# Changelog

All notable changes to e-workbench are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The engine is consumed from git and never published, so nothing here is released: `[Unreleased]` records the
milestones it has reached.

## [Unreleased]

### Added

- Fleet entry `fleet/e-track.toml`: edamlabs/e-track (lib, eager) — deps, security, drift, release, docs,
  community; the run-tracking library leaves `labs/etrack` for its own repository and PyPI.
- deeptrack on the settings law (proj-py-layout `references/settings.md`): one `Settings(InfraSettings, ProviderSettings,
  OntologySettings, ServiceSettings)`, UPPERCASE fields named as their variables, no prefixes, no discovery; only the
  root (main, the ASGI app, the lifespans, the cli commands) reads `st`, drivers take keyword arguments. The 31
  environment names held against a snapshot taken from the old composer; one precedence for every key (kwargs > env >
  .env — no pinned dotenv source: a stale shell `GEMINI_API_KEY` is the shell's to clean). Gates: uppercase, one cluster per name, the snapshot, root-only
  reads, types-only below the root — seen red on an injected read. 116 unit, 21 integration, 15 real-model.
- deeptrack audited against e-nous core 61db22f (`TODO_audit`): no loose helpers left (CLI commands as plain handlers
  over a `ChatSession`, one `lifespan` per module, per-arm assembly as `ArmsService` at `state.services.arms`, the
  AG-UI stream as `RunAgui`); capability-first brand names (`ChatGeminiDriver`, `ClassifyGeminiDriver`); `ValidationPort`
  in `ports/`; no `ty: ignore`; beartype on business classes; every test async, no helper inside a test module (17
  conftests). Gates: 110 unit, 21 integration, 15 real-model. Vendored-spine findings left for e-arkhetypo.
- deeptrack on e-track 0.3.0: every node of the graph declares its label and its nature (`EventKind`) — the canvas
  reads «Guardia de entrada · evaluation», «Modelo del agente · llm», striped by family; deepagents' own nodes named by
  id. e-track 0.3.0 also tracks log-only (`EventChannel()` without a bus). 111 unit, 21 integration.
- deeptrack on e-track 0.4.0 (e-track's `TODO_canvas`): the viewer is the declared graph built once and only lit — no
  node hides or moves mid-run (measured: 0 hidden, one viewport over a live run) — with single-word node labels
  (Guardia, Validación, Aprobación, Ejecución, Modelo, Herramientas, Reparación, Cierre). 111 unit, 21 integration.
- deeptrack on e-track 0.1.3 (`TODO_events`): Langfuse fed only by etrack's bus over OTLP — the A/B against Langfuse's
  own handler (same runs) found no lost row once e-track priced usage in exclusive buckets (0.1.2), and no orphaned root;
  agent versions ride every trace's root span; etrack's live canvas mounted at `/etrack` on deeptrack's server, its own
  viewer removed. LangSmith not measured (no key); the marvin trial dropped (marvin is a source of ideas only).
- TODO_viewer transferred to e-track: the live viewer (topology + span tree over SSE, React Flow canvas) ships as
  `e-track[viewer]` on Litestar + granian; deeptrack mounts it instead of keeping its own track API.
- deeptrack agents as data (`TODO_harness`): `src/` flat (api, logic, models, services, tools at the level of infra; no
  project package), per-layer state branches with an OST parity test; the four agents moved byte-identical into
  `labs/deeptrack/agents/*.md` (YAML frontmatter + instructions; shared `skills/` and `CONTEXT.md`), loaded and checked
  at startup by a files harness driver (7 laws) and built by a deepagents adapter (5 laws); e-track 0.1.0 from PyPI
  tracks every run on a bus with live, console and OTLP sinks; a per-agent evaluation tier (holdout, k-of-n). Gates:
  108 unit, 23 integration, 15 real-model, holdout 7/7.
- `labs/`: the home of experiments bound sooner or later for production or another project.
- `labs/deeptrack` (`TODO_deeptrack`): an insurance deep agent (orchestrator + ontologist, queries, transactions)
  over two Open Ontologies MCP servers, with a deterministic SHACL gate, a human approval interrupt, an enum input
  guard in parallel with the agent, Gemini over its API key, live `RunEvent` frames and Langfuse v4, an AG-UI server
  and a CopilotKit UI — all in one lab stack (`labs-*`, ports 28100–28199). House taxonomy (ports, drivers, engine,
  processor, layered lifespans), 71 unit · 21 integration · 15 real-model tests. A pre-registered A/B
  (`labs/deeptrack/BENCH.md`, 3 revisions): the shapes catch every violation the agent cannot read (0/12 without
  them); after the agent is the right position; the ontologist adds nothing on this domain. Langfuse audit moved
  to `TODO_events`.
- `labs/etrack` (`TODO_etrack`): e-track, a framework-agnostic run tracking library on the e-arkhetypo library stack —
  one `RunEvent` model (13 kinds with a `custom` fallback, five phases, typed delta parts incl. reasoning) carried by
  a structlog channel of its own, fanned out by a bounded anyio bus to parallel sinks that each read their own view:
  OTLP spans and logs with run-derived W3C ids (GenAI, OpenInference and Langfuse attributes), a live per-thread
  replay buffer. LangGraph/deepagents enter through a callback source; a topology adapter and a layout processor
  map the declared graph. 271 unit tests, 98.7 % coverage; not published, not yet imported by deeptrack.
- `labs/etrack` proven (`TODO_sandbox`): 100 % line and branch coverage over in-process fakes (a fake OTLP/HTTP collector
  decoding the real protobuf); a compose sandbox (one OTel Collector, file out) and an e2e tier that runs a deep agent
  into it — it caught LangChain objects breaking the OTLP sink, now encoded by that driver through e-serde.
- Fleet (`TODO_jev`): `e-jev` onboarded (`edamlabs/e-jev`, service · eager, moved from `damvolkov` on 2026-10-28) with
  `deps`, `drift` and `community`; its manifest declares `[tool.edamlabs]` and `drift` reports ok.
  `security`, `docs` and `release` stay off until the repo carries workflows and a docs site — its image is
  still a private user package, `ghcr.io/damvolkov/e-jev`.
- M5 · community (`TODO_community`): deterministic triage of a repository's open third-party issues and pull
  requests. A `community` label marks what the engine has seen, an issue with no body earns a request for the
  reproduction it lacks and the `needs-repro` label, idleness past `stale_days` earns the `stale` label and a
  warning naming the day it closes, and idleness past the warning closes the item with its idle age. Insiders,
  automation and drafts are never spoken about; the engine never approves and never merges a third-party pull
  request. Enabled on all six fleet entries.

### Changed

- Renamed esteward → e-workbench (`TODO_workbench`): distribution and CLI `e-workbench`, package `e_workbench`,
  environment prefix `E_WORKBENCH_`; issue labels, act/release branches, issue markers and bot identity follow.
- Detached from the personal toolchain: the engine's public record no longer names it. The decision log
  speaks of "the personal toolchain" and "a private blueprint repository" where it named the repositories;
  the blueprint's pending work left the backlog plan — it belongs to that repository's own plan, not to the
  watcher's. Done in `TODO_detach`.
- README: badge layout, description and identity line standardized on the e-serde template; the verdict ladder
  kept as its own table under the identity line. Done in `TODO_README` and `TODO_fleetreadme` across the fleet.
