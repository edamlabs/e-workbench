# Decisions

### 2026-10-22 · A public engine of its own, in edamlabs

**Decision.** Maintenance of EDamLabs projects lives in `edamlabs/e-workbench`, public. The personal toolchain
stays private and personal: it mounts projects and harnesses, it does not maintain them.

**Evidence.** The fleet is public (libraries and dockerizable services); the engine acting on it is shared
infrastructure, not personal tooling. A private engine could not be installed by public repositories' CI
without a cross-identity token.

**Rejected.** A `maintain` command bolted onto the personal toolchain (mixes it with organisation
infrastructure); a PyPI package (see below).

### 2026-10-22 · Consumed from git, never published

**Decision.** e-workbench is not published to PyPI. Workflows check it out at the commit they run from.

**Evidence.** Engine and workflow versions can never drift; a release is a git tag; nobody outside EDamLabs
installs it.

**Rejected.** PyPI: a second version to keep aligned and a release pipeline with no consumer.

### 2026-10-22 · The fleet lives here

**Decision.** Every project's maintenance contract is `fleet/<repo>.toml` in this repository; projects carry
only the thin callers that events require (PR and issue events fire in their own repository).

**Evidence.** One place to read and change what the organisation maintains; a module change and its
configuration change land together.

**Rejected.** A `maintain.toml` in each project: N copies of the same thresholds to keep in step.

### 2026-10-22 · Autonomous, deterministic, one issue per incident

**Decision.** Verdicts are `ok | watch | act | escalate`, decided by thresholds and by what hosts, registries
and advisory databases report. Escalations open one issue each, keyed by a marker, updated while they
persist and closed when they clear; one pinned status issue per repository holds the rest.

**Evidence.** Phantom-pin detection verified on a private blueprint repository: 10 pins naming no commit found,
matching the manual audit; etrafilatura: 6 healthy dependencies, 14 resolving pins, 212 locked packages queried.

**Rejected.** Pull requests for every finding (a human would review a junior's work); an LLM judging health (a
deterministic check exists for every signal).

### 2026-10-22 · Runtime typing with beartype

**Decision.** `beartype_this_package()` in the package hook; ruff's TC001–TC003 disabled.

**Evidence.** beartype resolves annotations at runtime; imports moved under `TYPE_CHECKING` would not resolve.

**Rejected.** Static checking only (the house checks types twice).

### 2026-10-22 · Uncached loggers

**Decision.** `cache_logger_on_first_use=False`, stderr resolved per call.

**Evidence.** A cached logger kept a closed stderr across captured runs (order-dependent test failures); a CLI
emits tens of events, the cost is nil.

**Rejected.** Caching with per-test resets (fixes tests, keeps the redirection hazard in production).

### 2026-10-22 · Issue listings are read three times; duplicates converge

**Decision.** `GithubAdapter.issues` unites three reads of the listing; the planner keeps the oldest issue per
dashboard or incident key and closes the rest as duplicates.

**Evidence.** The second fleet run on etrafilatura opened a second status issue (#14 beside #13). Measured with
fresh installation tokens, scoped and unscoped: the labelled listing answered an empty 200 in 2 of 16 reads.
Three united reads bring a false empty from ~12 % to ~0.2 %; convergence repairs what remains on the next run.

**Rejected.** Trusting one read (duplicates); storing issue numbers outside GitHub (state to keep in sync);
GitHub search (eventually consistent as well).

### 2026-10-26 · Moved repositories are followed once and watched

**Decision.** The GitHub adapter follows one 301/302/307/308 from a moved repository; the deps module turns a
moved repository into a `watch` finding naming the new location; a second redirect raises.

**Evidence.** e-workbench's own fleet entry crashed on `jcrist/msgspec`, which answers 301 since it moved to
`msgspec/msgspec`: wreq does not follow redirects, and the redirect body has no `archived` field.

**Rejected.** Enabling wreq's redirect following globally (hides the move the fleet should record).

### 2026-10-26 · An advisory's fix is the fix of the locked version's branch

**Decision.** The OSV adapter reports as `fixed` the end of the `introduced <= locked < fixed` interval holding the
locked version (versions compared with `packaging`, semver's `-0` read as the version itself); a version in an open
interval has no fix; an unparsable version falls back to the first fix listed.

**Evidence.** anytomd's `webpki-roots` 1.0.9 was reported "fixed in 0.26.11" — the fix of the 0.26 branch; its
branch is fixed in 1.0.10.

**Rejected.** The first fix listed (wrong across release branches); a semver library per ecosystem (PEP 440
ordering holds for the released versions OSV lists).

### 2026-10-26 · Two identity axes: kind and family

**Decision.** Every repository declares `kind` (`lib` | `service`; desktop binaries next) and `family` (`eager` |
`binding` | `infra`) in `pyproject.toml` `[tool.edamlabs]`; the fleet entry repeats them; the `drift` module acts
on a missing declaration and escalates a contradiction.

**Evidence.** What a project ships decides its release path (PyPI or GHCR); what it is decides its contract (a
binding keeps its upstream's syntax, an eager product defines its own). The two vary independently: a binding is
a lib today, an eager product can be either.

**Rejected.** One combined category (conflates delivery with nature); PyPI classifiers (no vocabulary for either
axis); declaring identity only in the fleet (the repository would not say what it is).

### 2026-10-26 · One finding per package, not per advisory

**Decision.** The deps module reports the advisories of one package version and kind as a single finding: the
count, the first five ids, and the version that clears them all (the highest fix; none when one advisory has no
fix, which escalates the package). The incident key is `deps:advisory:<kind>:<package>@<version>`.

**Evidence.** e-serde's lockfile carried 44 Pillow advisories: 44 rows of one fact ("upgrade Pillow") in the status
issue. One row per package keeps the dashboard readable and the action single.

**Rejected.** One finding per advisory (noise); dropping advisory ids (the evidence would leave the dashboard).

### 2026-10-26 · act executes lockfile-only bumps, one self-merging PR per finding key

**Decision.** `e-workbench run --act` carries out the fixable vulnerability findings whose fix is a lockfile-only
bump: `cargo update -p <name>@<locked> --precise <fix>` / `uv lock --upgrade-package <name>==<fix>`, verified by
re-parsing the lockfile (the fix pinned, the vulnerable version gone), committed to `e-workbench/act/<key-slug>`,
pushed, and opened as a PR with squash auto-merge. One branch per finding key makes a re-run idempotent: the PR
is updated, never duplicated. A bump that needs a manifest range change is out of the slice and escalates.

**Evidence.** Every `act` finding of the fleet today (zip 0.6.6/2.6.1, zstd 0.13.3, zstd-safe ×2 on e-voice;
zip 8.6.0 on anytomd) is pinned by an upstream range: the solver's failure plus the reverse tree proves it
without judgement. The lockfile itself is the verification: a solver that reports success without moving it
escalates instead of pushing.

**Rejected.** LLM-driven repair (a deterministic solver exists for every case of the slice); editing manifests
(range semantics are a human decision); a sibling act.yml (the status row must link the PR in the same publish
pass, so run and act share one report).

### 2026-10-26 · Blocked upstream is watch, not escalate

**Decision.** A fix the solver cannot reach because an intermediate package pins the vulnerable range becomes
`watch`, its detail carrying the reverse dependency chain (`zip 0.6.6 ← npyz 0.9.1 ← e-voice-tts`); a fix only
the project's own manifest blocks escalates. The chain is the first-child walk of `cargo tree -i` /
`uv tree --invert`: a workspace member at depth 1 means the manifest, an intermediate registry package means
upstream.

**Evidence.** An escalation opens an issue asking the project to act; against npyz's `zip ^0.6` no downstream
action exists, so the issue would ask forever — the ask belongs to an upstream draft, and the dashboard row
keeps the evidence visible. The manifest case is the project's own decision, so it escalates.

**Rejected.** Escalate for both (issues that cannot be acted on train humans to ignore issues); watch for both
(a manifest block is actionable downstream; staying silent would hide work).

### 2026-10-26 · The status issue is pinned from the plan, skipped at apply when already pinned

**Decision.** `StatusDashboard.plan` emits `PinIssue(kept.number)` on every run whose status issue exists;
`GithubAdapter` reads `pinnedIssues` over GraphQL and only sends `pinIssue` when the issue is not among them.
A first run creates the issue and the pin converges on the next run.

**Evidence.** The REST API has neither the pin nor the pinned state — GraphQL is the only read, so the planner
cannot know the state without fetching it; one read per run at apply time is the cheapest place for the
idempotence the spec asks for. The operation joins the exhaustive `match` ending in `assert_never`.

**Rejected.** Fetching pinned state for the planner (an extra read to save one write); pinning at creation
(the create apply answers no number; a contract change for a first-run cosmetic).

### 2026-10-26 · Agnostic operations live in ops/, and logic lives in its class

**Decision.** A new `ops/` layer holds operations that know no domain; `logic/url.py` becomes `ops/url.py`,
its three loose functions one class `Url` that parses the URL once and shares the segment cut through a
private. The same correction falls on the advisory grouping (`GroupAdvisories`) and the reverse-tree chain
(`ChainBump`). Loose module functions survive only as dispatch handlers (`parse_lockfile`) and entrypoints.
tach: `ops` depends on nothing; `logic` depends on `models` and `ops`.

**Evidence.** URL decomposition knows nothing of fleets or findings; it sat in the domain layer because that
is where its only caller lived. One parse per URL, shared by every cut, is the optimisation a class gives and
three loose functions never did. furl was weighed: the house rule reaches for it on URL treatment except when
the treatment is very simple, and three stdlib cuts are the simple case.

**Rejected.** Keeping the functions in `logic/` (agnostic operations in the domain layer); furl (a dependency
for three `urlsplit` cuts); one utility module per helper (the path names the module, the class holds the
logic).

### 2026-10-26 · The release mechanism lives once, in e-workbench; repositories keep tag-driven publishing

**Decision.** The release policy (content in `## [Unreleased]` gates, a Fixed/Security entry releases at
once, anything else once the oldest unreleased commit passes the fleet entry's `unreleased_age_days`;
patch by default, minor on `### Added` or a `feat:` commit, a breaking marker escalates) and its execution
both live in e-workbench. The stage folds the changelog line for line like e-serde's proven awk (golden-tested
against its output), bumps the static version fields, re-syncs the root lockfiles, opens one self-merging
`chore(release): vX.Y.Z` PR per version, and pushes the tag onto that PR's merge commit on a later run.
Repositories keep only the tag → build/publish half of their release flow. The module is enabled per fleet
entry as repositories converge: etrafilatura and anytomd first, whose `release.yml` already triggers on
`v*` pushes.

**Evidence.** The same actions — bump, fold, PR, tag — already existed once (e-serde's `release.yml`) and
would have needed copies in three more repositories; the organisation's instruction is to align same-action
files to the newest of them and to keep what can be common in e-workbench. Tagging on a later run instead of
polling for the merge keeps a fleet run bounded, and every intermediate state converges: a folded version
without its tag is a `watch` row, and the next run tags it. Live dry runs on etrafilatura and anytomd print
the decisions (`no unreleased content`, tag and changelog agreeing).

**Rejected.** Copying e-serde's `release.yml` into the tag-driven repositories (four copies of one
mechanism, drifting — the original TODO's preference, superseded by the centralisation instruction);
e-workbench dispatching each repository's release workflow (the mechanism still lives in five places);
blocking the run until the release PR merges (a twenty-minute poll whose failure mode needs the same
cross-run state anyway); automating a major release (a breaking marker escalates instead).

### 2026-10-27 · Upstream parity is declared in the fleet entry, not in the repository

**Decision.** The `upstream` module reads each binding's parity baseline from `fleet/<repo>.toml`
(`[[upstream.engines]]`: name, registry, parity). The repository keeps owning the mirror (its sync flow) and
the API diff (its `apidiff` tooling); e-workbench owns only the detection of an engine that moved.

**Evidence.** The repositories hold parity implicitly — etrafilatura's byte-parity goldens are rewritten
against whichever Python trafilatura is installed, and `apidiff` takes its versions as arguments — so no
record inside them names the version the API mirrors. The fleet entry is already the maintenance contract;
a parity that must be updated by hand belongs beside the thresholds that are.

**Rejected.** Deriving parity from the locked engine version (Renovate bumps the lock without re-mirroring
the API; the two move for different reasons); a parity file per repository (a second contract to keep in
step with the fleet entry).

### 2026-10-27 · The docs module runs `make docs`, and every `make docs` is strict

**Decision.** The engine invokes the repository's own docs target (`make docs`) instead of a hardcoded
zensical argv; the sweep made every repository's target strict (`--strict` added where missing) and gave the
three repositories without a deploy workflow the proven `docs.yml` (build with `make docs`, upload the site,
deploy-pages behind the `DOCS_DEPLOY` gate). e-voice defers the pages-version check until its per-image
release policy exists.

**Evidence.** gliner builds with a pinned `uvx zensical` and e-voice generates its OpenAPI documents with
cargo before building: a single hardcoded argv cannot honour both toolchains, while `make docs` is the
contract each repository already exposes to a workstation. The gates were inert (`DOCS_DEPLOY` unset) and
two sites had no deploy path at all, which is exactly why three Pages sites served stale versions.

**Rejected.** A hardcoded zensical argv in the engine (fails on the uvx repositories, skips e-voice's
OpenAPI step); dropping `--strict` from the engine's build (the TODO names the strict build as the check);
comparing e-voice's Pages against a repository tag (its releases are per image).

### 2026-10-27 · Triage is for strangers: automation is read from the login, not the association

**Decision.** The `community` module triages an open item only when a stranger owns it. An insider is
`OWNER`/`MEMBER`/`COLLABORATOR`; automation is an author whose login ends in `[bot]`; a draft pull request is
work its author marked unfinished and is counted but never spoken about. The engine never approves and never
merges a third-party pull request: no such operation exists in its vocabulary.

**Evidence.** `gh api` over the fleet's open items (2026-10-27): `eself-maintenance[bot]` reports its own
status and escalation issues as `CONTRIBUTOR` or `NONE`, and `renovate[bot]` as `CONTRIBUTOR` or `NONE`. An
association-only rule would therefore have labelled the engine's own pinned status issue `community` and,
after `stale_days + close_days`, closed it and every Renovate issue — the dashboard is the module's output,
so the run would have destroyed its own record. Live dry runs on all six repositories after the guard print
`0 open third-party items` and no community escalation.

**Rejected.** Trusting `author_association` alone (measured above to be wrong for app-authenticated actors);
reading `user.type == "Bot"` (a field the listing already answers with the login suffix — one more read for
the same fact); a dedicated `--community` flag mirroring `--act`/`--release` (the triage is deterministic,
reversible by simply replying, and `--publish` is already the line between planning and carrying out);
creating the three labels fleet-wide before enabling (measured on a scratch repository: `POST
/issues/{n}/labels` auto-creates an unknown label with the default colour, so no bootstrap is required —
a colour and description pass remains cosmetic and Damien's to schedule).

### 2026-11-03 · Run tracking is its own library, and the log is its bus

**Decision.** Event tracking for agent runs lives in `labs/etrack` (e-track): one `RunEvent` model whose field names
are the reserved keys of a structlog channel of its own; the channel validates, publishes on a bounded per-sink bus
and forwards a narrowed line to the host's logger. Frameworks enter through sources (LangGraph callbacks today),
clients through sinks that declare a partial view (OTLP for Langfuse, LangSmith and any collector; live replay for a
canvas). Its spine lives inside the package (`etrack.infra`, …), not at `src/` root.

**Evidence.** deeptrack's projector already proved callbacks see every span with ids for free; InstrumentGraph
cannot instrument a graph it did not build (subclass of `StateGraph`, node contract, `RunState` by reference — no
checkpointer); marvin produces events through four routes. A per-module spine placement cannot reach marvin, which is
not arkhetypo-shaped; a top-level `infra` package would merge with the consumer's in site-packages. Measured: one
emission costs the producer p50 4.8 µs, p99 8.5 µs (2 000 frames, bus + sink, no forwarding).

**Rejected.** An event bus with the logger as one more sink (two models to keep aligned); the host's logger as the
bus (its level filter would drop events); scattering the pieces over deeptrack's spine (portable module by module,
not as a system); extending InstrumentGraph; native Langfuse/LangSmith handlers as the primary path (kept as the
baseline arm of the A/B in `TODO_events`).


### 2026-11-03 · etrack's e2e sandbox is one collector writing to a file

**Decision.** `labs/etrack/compose.yml` runs one OpenTelemetry Collector (contrib 0.162.0): OTLP/HTTP in, OTLP/JSON
files out; the e2e tier reads them back by trace id. Unit tests fake every outbound service in process (an HTTP
server decoding the real OTLP protobuf); coverage is gated at 100 %.

**Evidence.** The collector is the one service every OTLP backend sits behind, and its files show exactly what left
the process — spans and logs — with no query API to learn. The first e2e run found a defect the unit tier missed
(LangChain objects in payloads broke the OTLP sink).

**Rejected.** Langfuse as the sandbox (six containers; it is deeptrack's A/B, not etrack's contract); Jaeger (traces
only, logs unverifiable); the collector's `debug` exporter read from container logs (unstructured).

### 2026-11-03 · deeptrack's agents are data, the app has no project package

**Decision.** Agents are markdown files outside the code (`labs/deeptrack/agents/`): YAML frontmatter (name,
description, tier, tools, middleware, skills, subagents) and the instructions as the body; skills shared by name;
siblings only, hierarchy declared in `subagents`. A provider-agnostic harness port (`AgentSpec`, `Agent`, `Roster`) is
filled by a files driver and built by a deepagents adapter; the contract is checked at startup, intrinsic laws in the
driver, cross-references in the build. `src/` has no project package: system folders sit at the level of `infra`.

**Evidence.** Agent Skills (SKILL.md) and markdown-with-frontmatter agents are the convergent format (deepagents,
Codex, Claude Code subagents); declarative YAML wiring is experimental in ADK, preview in Microsoft Agent Framework,
in flux in CrewAI; marvin's Python-string prompts patched by `.replace()` fail silently. The migration was proven
byte-identical per A/B arm (prompts, descriptions, tools, middleware), then 15/15 real-model questions and a 7/7
holdout. Without the package wrapper, `state.services.chat` ≡ `services/chat.py` (OST) holds.

**Rejected.** One directory per agent with code inside (couples data to code); nested subagents (reuse unknown, deep
agents run one level); a declarative YAML for wiring (immature everywhere); the old silent drop of a tool a server
does not advertise (law TOOL now stops the boot).

### 2026-11-03 · Langfuse is fed from etrack's bus, not from its own handler

**Decision.** deeptrack sends runs to Langfuse through etrack's `OtlpDriver` (Langfuse's OTLP endpoint) and drops
Langfuse's `CallbackHandler`, once e-track 0.1.1 is published.

**Evidence.** `make tracing` (`labs/deeptrack/tests/benchmark/tracing.py`): both arms on the same runs, Gemini 2.5 Flash,
15 runs. Lag to a stable trace p50 1.04 s / p95 1.06 s in both (1 s poll); generations with usage 70/70 in both, tokens
equal (211 414); subagents nested 10/10 in both; 4 fewer observations per run by the bus (plumbing folded); one orphan
per run in the native arm (its root hangs from a span it never exports), none by the bus. The one lost row — cost,
up to 2× native because cached input was priced at the full rate — was an e-track defect, fixed with exclusive usage
buckets: after it, cost identical and 0/31 generations differ.

**Rejected.** Keeping both (two traces per run, two ids to correlate); the native handler alone (an extra framework
dependency per backend, orphaned roots). LangSmith not measured: no API key; self-hosted needs Enterprise.


### 2026-11-03 · deeptrack's A/B arms are a service in the state tree, not lifespan helpers

**Decision.** The per-arm assembly (roster with or without the ontologist, which validation the gate and the proposing
tools run) is `services/arms.py` `ArmsService`, mounted at `state.services.arms`; the bench and the arm tests ask it
for `chat(arm)`. Each lifespan module is one `lifespan` context manager (the e-arkhetypo form); the ontology and track
branches have their own, entered by the providers lifespan. The engines branch holds both validations (`shacl`,
`passing`); the arm→validation table lives once, in the service.

**Evidence.** Audit against e-nous core 61db22f: tax-py-naming 4 (no loose functions outside `ops/` and dispatch)
flagged `built`, `agent`, `chat`, `tracker`, `versions`, `opened`, `langfuse`, `track`, `ontology` and the CLI's
`_chat_*`. After the change: 110 unit, 21 integration, ty and tach clean. ty 0.0.96 (latest) refuses a protocol whose
`__aenter__` returns `Self` as an `AbstractAsyncContextManager` (`CoroutineType[..., ChatPort]` not assignable to
itself): the sinks table is typed by its concretions and the injectable chat crosses with one reasoned `cast`; the
graph's TypedDict schema crosses as `Any` for the same class of checker gap — no `ty: ignore` left.

**Rejected.** Keeping a generic `opened[P]` helper (a loose function, the very finding); an arm parameter on the whole
lifespan (the bench would reopen MCP sessions per arm and lose the shared warm stack); `ty: ignore` (banned).
