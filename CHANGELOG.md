# Changelog

All notable changes to e-workbench are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The engine is consumed from git and never published, so nothing here is released: `[Unreleased]` records the
milestones it has reached.

## [Unreleased]

### Added

- `labs/`: the home of experiments bound sooner or later for production or another project.
- `labs/deeptrack` (`TODO_deeptrack`): an insurance deep agent (orchestrator + ontologist, queries, transactions)
  over two Open Ontologies MCP servers, with a deterministic SHACL gate, a human approval interrupt, an enum input
  guard in parallel with the agent, Gemini over its API key, live `RunEvent` frames and Langfuse v4, an AG-UI server
  and a CopilotKit UI — all in one lab stack (`labs-*`, ports 28100–28199). House taxonomy (ports, drivers, engine,
  processor, layered lifespans), 71 unit · 21 integration · 15 real-model tests. A pre-registered A/B
  (`labs/deeptrack/BENCH.md`, 3 revisions): the shapes catch every violation the agent cannot read (0/12 without
  them); after the agent is the right position; the ontologist adds nothing on this domain. Langfuse audit moved
  to `TODO_events`.
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
