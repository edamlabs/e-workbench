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
