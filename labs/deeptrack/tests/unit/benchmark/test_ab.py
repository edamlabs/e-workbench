"""The bench's own logic: the rotation is balanced, a case is judged by its one outcome, clusters are per case."""

from collections import Counter

import numpy as np
from etrack.models.event import RunEvent

from models.arm import Arm
from tests.benchmark.ab import AbBench, AbSummary, Case
from tests.unit.benchmark.conftest import Make


async def test_ab_rotation_balanced() -> None:
    arms = (Arm.FULL, Arm.NO_ONTOLOGIST, Arm.NO_ONTOLOGY)
    orders = [AbBench._run_order(repeat, index, arms) for repeat in range(3) for index in range(3)]
    assert all(sorted(order) == sorted(arms) for order in orders)
    assert all(Counter(order[place] for order in orders) == Counter(dict.fromkeys(arms, 3)) for place in range(3))


async def test_ab_rotation_two_arms() -> None:
    arms = (Arm.FULL, Arm.PREVALIDATE)
    firsts = Counter(AbBench._run_order(repeat, index, arms)[0] for repeat in range(2) for index in range(2))
    assert firsts == Counter({Arm.FULL: 2, Arm.PREVALIDATE: 2})


async def test_ab_judge_outcomes(valid_case: Case, invalid_case: Case, proposed: list[RunEvent]) -> None:
    assert AbBench._run_judge(valid_case, proposed, {"propuesta": valid_case.expect}, None) == (True, "nobody")
    assert AbBench._run_judge(valid_case, proposed, {"propuesta": {"type": "endoso"}}, None) == (False, "nobody")
    assert AbBench._run_judge(invalid_case, proposed, None, None) == (True, "gate")
    assert AbBench._run_judge(invalid_case, [], None, None) == (True, "agent")
    assert AbBench._run_judge(invalid_case, [], None, "abuso") == (True, "guard")
    assert AbBench._run_judge(invalid_case, proposed, {"propuesta": {}}, None) == (False, "nobody")


async def test_ab_clusters_one_value_per_case(sample: Make) -> None:
    samples = [
        sample(Arm.FULL, "a", 0, True),
        sample(Arm.FULL, "a", 1, True),
        sample(Arm.NO_ONTOLOGY, "a", 0, False),
        sample(Arm.NO_ONTOLOGY, "a", 1, True),
        sample(Arm.FULL, "b", 0, True),
        sample(Arm.NO_ONTOLOGY, "b", 0, True),
        sample(Arm.FULL, "c", 0, True),
        sample(Arm.NO_ONTOLOGY, "c", 0, None),
    ]
    clusters = AbSummary(samples)._clusters(Arm.FULL, Arm.NO_ONTOLOGY)
    assert clusters.tolist() == [0.5, 0.0]


async def test_ab_interval_degenerate_and_spread() -> None:
    assert AbSummary._interval(np.array([1.0, 1.0, 1.0])) == (1.0, 1.0, 1.0)
    mean, low, high = AbSummary._interval(np.array([0.0, 1.0] * 10))
    assert mean == 0.5
    assert low < 0.5 < high


async def test_ab_latency_clusters_use_the_median(sample: Make) -> None:
    samples = [
        sample(Arm.FULL, "a", 0, True, 9000.0),
        sample(Arm.FULL, "a", 1, True, 3000.0),
        sample(Arm.FULL, "a", 2, True, 5000.0),
        sample(Arm.PREVALIDATE, "a", 0, True, 2000.0),
        sample(Arm.PREVALIDATE, "a", 1, True, 2000.0),
    ]
    assert AbSummary(samples)._clusters(Arm.FULL, Arm.PREVALIDATE, "latency_ms").tolist() == [3000.0]
