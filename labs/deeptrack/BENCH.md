# BENCH — what the ontology layer is worth (A/B, pre-registered)

Written 2026-11-03, before the first run. Nothing below changes after seeing results; a change is a new
pre-registration with its own date.

## Question

Does the ontology layer make the agent's transactions correct more often than the same agent without it?

## Arms (one variable each; same model, data, stack, graph topology, guard)

| Arm | Ontologist subagent | SHACL gate | Reading |
|---|---|---|---|
| `full` | yes | judges against `ontology/formas.ttl` | the system as built |
| `no_ontologist` | no | judges | reading (a): only the subagent removed |
| `no_ontology` | no | judges nothing (every proposal conforms) | reading (b): the layer removed — **baseline** |

The policies' data store (`labs-ontoref`) stays in every arm: it is the database, not the layer under test.

## Cases (`tests/benchmark/deeptrack/cases.json`)

7 transaction cases, each with one correct outcome:
- **valid** (2): the run must stop for approval with exactly the expected proposal.
- **invalid** (5): the run must never stop for approval — out of term (2), coverage with an open claim, coverage not
  in the policy, policy that does not exist.

## Primary metric and threshold

- **Metric:** per-sample correctness (1/0) of the case's outcome.
- **Hypothesis H1:** `full` − `no_ontology` > **0.20** (twenty points of correctness).
- **Decision:** paired bootstrap (percentile, 95 %, 10 000 resamples) of the mean per-sample difference, samples paired
  by (case, repeat). Interval above +0.20 → the layer is worth it; interval crossing +0.20 → undecided at this n;
  interval below +0.20 → not worth it at this threshold.
- **Secondary contrast (reported, not decided on):** `full` − `no_ontologist` — what the subagent adds on top of the gate.

## Recorded, never used to pick the winner

Who stopped each invalid case (agent · gate · nobody), latency p50/p95 per arm, tokens in/out per sample, model and MCP
calls per sample.

## Protocol

- Repeats: pilot r = 3 (21 paired samples per arm); n is revised from the pilot's spread, as a new entry here.
- Interleaving: for each repeat, for each case, the three arms in a rotated order — drift cancels, never biases.
- Warm-up: one discarded turn per arm before the first measured one.
- Each sample is a fresh thread. Model: Gemini 2.5 Flash (chat), Gemini 3.5 Flash-Lite (guard), API defaults.
- Raw samples: `reports/ab-<timestamp>.jsonl`; summary beside it. Versions and date in the summary.

## 2026-11-03 — pilot result, and a protocol revision (made after seeing it, so declared as such)

Pilot r = 3, 63 samples, 0 failures (`reports/ab-20261103T123130.*`, not committed). Pre-registered decision:
`full` - `no_ontology` = +0.43, 95 % [+0.24, +0.62] over 21 pairs → worth it.

Validity flag: outcomes are near-deterministic within a case (repeats agree), so the 21 pairs are 7 clusters, not 21
independent samples. The case-clustered bootstrap gives +0.43, 95 % [+0.14, +0.86] — it crosses +0.20. The pairs
interval is too narrow for this design.

Revision for the next run (new pre-registration): resample by case (cluster bootstrap), and grow the case set to at
least 20 transaction cases — n comes from the cases, not from the repeats; r = 2 is enough to catch flakiness.

## 2026-11-03 — revision 2, registered before its first run

- **Cases:** 20 transaction cases (8 valid, 12 invalid), `tests/benchmark/deeptrack/cases.json`, over an extended
  fictitious data set (`ontology/datos.ttl`: pol-3003, pol-4004, an open and a closed claim). Every case's expected
  outcome was checked against the SHACL engine before any agent ran: 20/20 agree.
- **Unit of analysis:** the case. Per case, the mean over repeats of `full` - `no_ontology`; the 95 % interval is a
  percentile bootstrap resampling cases (10 000 resamples, seed 7).
- **Repeats:** r = 2 (catches flakiness; power comes from the cases).
- **Hypothesis, metric, threshold:** unchanged — H1: `full` - `no_ontology` > +0.20 in correctness.
- **Secondary (reported, not decided on):** `full` - `no_ontologist`, same method.

## 2026-11-03 — revision 2, result

120 samples, 0 failures (`reports/ab-20261103T125235.*`, not committed). Pre-registered decision: `full` - `no_ontology`
= +0.28, case-clustered 95 % [+0.07, +0.50] → **undecided at this n**. Secondary `full` - `no_ontologist`: -0.03
[-0.07, +0.00].

What the cases show, by kind of violation (invalid cases, samples that reached approval):

| Violation | Cases | `full` | `no_ontologist` | `no_ontology` |
|---|---|---|---|---|
| out of term (after, before, day before) | 4 | 0/8 | 0/8 | **8/8** |
| coverage with an open claim (endorsement) | 2 | 0/4 | 0/4 | **4/4** |
| coverage not contracted | 4 | 1/8 | 0/8 | 0/8 |
| policy does not exist | 2 | 0/4 | 0/4 | 0/4 |

Reading: the agent alone catches what it can read in the policy (coverages, existence); it never catches the rules
that live only in the shapes (term dates, open claims) — the gate catches all of them. Overall correctness dilutes
that: valid cases (8) and agent-caught invalid ones (6) carry no difference by construction, so the mean is fixed by
the case mix, not by the layer. The one `full` failure (not-covered, pol-4004) did not reproduce in 4 reruns; the
sample did not record what reached approval — it does now (`proposal`, `trace_id`).

Proposed revision 3 (not run; for Damien to accept): primary metric = **escape rate of invalid transactions** (share
of invalid cases that reach approval), per arm and per kind of violation — the question asked, without the dilution.

## 2026-11-03 — closing the "is it worth it" question; revision 3 asks "where does it go"

Closed (Damien, 2026-11-03): the layer's value as a deterministic validator is structural — rules that live only in the
shapes are never caught by the agent and always by the gate. More samples would add decimals, not knowledge.

**Revision 3 — position of the validation, registered before its first run.**

- **Arms:** `full` (the shapes judge after the agent proposes: the gate node) vs `prevalidate` (the same engine judges
  inside the proposing tools, before the proposal lands; the gate stays as a second line). One variable: the position.
- **Question:** does validating inside the agent's loop cost less than validating after it?
- **Primary metric:** per-case median latency over repeats; contrast `full` - `prevalidate`; case-clustered percentile
  bootstrap (10 000, seed 7). **Threshold: +1000 ms** (prevalidate at least one second faster per case).
- **Guard rail on the decision:** the escape rate of invalid cases must stay 0 in `prevalidate`; any escape voids a
  "faster" verdict.
- **Recorded:** LLM calls, MCP calls, tokens per sample, who stopped each invalid case.
- **Cases, repeats:** the 20 cases of revision 2, r = 2, arms rotated per (repeat, case).
