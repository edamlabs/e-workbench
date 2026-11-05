"""tests/evaluation/agents/insurance: the entry agent judged on cases, k runs each — invariants always, behaviour k-of-n.

The cases are the bench's (`tests/benchmark/cases.json`, pre-registered); `split.json` holds out a fixed share, never
used to tune instructions: an optimizer proposes changes to `agents/` judged on `train` and accepted on `holdout`.
Invariants hold in every run (no node or run fails, nothing executes without approval, an invalid case never reaches
approval); the behaviour — a valid case reaches approval with exactly its expected proposal — holds in at least `NEED`
of `RUNS`. Each run's agents versions are recorded beside the verdict. `make eval` runs the holdout; `SPLIT=train` the rest."""

import json
from typing import Any

import pytest

from infra.state import State
from tests.evaluation.agents.insurance.conftest import RunOnce

pytestmark = [pytest.mark.evaluation, pytest.mark.llm, pytest.mark.integration]


async def test_insurance_case(
    state: State, run_once: RunOnce, runs: int, *, need: int, case: dict[str, Any], record_property: Any
) -> None:
    results = [await run_once(case) for _ in range(runs)]
    passed = sum(behaved for behaved, _ in results)
    record_property("passed", f"{passed}/{runs}")
    record_property(
        "versions", json.dumps({name: agent.version for name, agent in state.providers.harness.roster.agents.items()})
    )
    assert [broken for _, broken in results if broken] == []
    assert passed >= need, f"{case['id']}: behaved in {passed} of {runs} runs"
