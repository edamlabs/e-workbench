"""The bench's own logic: the rotation is balanced, a case is judged by its one outcome, clusters are per case."""

from collections import Counter

import numpy as np

from deeptrack.models.arm import Arm
from processors.models import EventKind, EventPhase, RunEvent
from tests.benchmark.deeptrack.ab import AbBench, AbSummary, Case, Sample

VALID = Case(id="v", kind="valid", message="m", expect={"type": "endoso", "poliza": "pol-1001", "quita": "cob-rc"})
INVALID = Case(id="i", kind="invalid", message="m")


def test_ab_rotation_balanced() -> None:
    orders = [AbBench._run_order(repeat, index) for repeat in range(3) for index in range(3)]
    assert all(sorted(order) == sorted(Arm) for order in orders)
    assert all(Counter(order[place] for order in orders) == Counter(dict.fromkeys(Arm, 3)) for place in range(3))


def proposed() -> list[RunEvent]:
    return [
        RunEvent(
            run_id="r", trace_id="t", seq=0, id="x", kind=EventKind.TOOL, phase=EventPhase.START, name="proponer_endoso"
        )
    ]


def test_ab_judge_outcomes() -> None:
    assert AbBench._run_judge(VALID, proposed(), {"propuesta": VALID.expect}, None) == (True, "nobody")
    assert AbBench._run_judge(VALID, proposed(), {"propuesta": {"type": "endoso"}}, None) == (False, "nobody")
    assert AbBench._run_judge(INVALID, proposed(), None, None) == (True, "gate")
    assert AbBench._run_judge(INVALID, [], None, None) == (True, "agent")
    assert AbBench._run_judge(INVALID, [], None, "abuso") == (True, "guard")
    assert AbBench._run_judge(INVALID, proposed(), {"propuesta": {}}, None) == (False, "nobody")


def sample(arm: Arm, case: str, repeat: int, correct: bool | None) -> Sample:
    return Sample(
        arm=str(arm),
        case=case,
        kind="invalid",
        repeat=repeat,
        correct=correct,
        stopped_by="gate",
        blocked=None,
        latency_ms=1.0,
        tokens_in=1,
        tokens_out=1,
        llm_calls=1,
        mcp_calls=1,
    )


def test_ab_clusters_one_value_per_case() -> None:
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


def test_ab_interval_degenerate_and_spread() -> None:
    assert AbSummary._interval(np.array([1.0, 1.0, 1.0])) == (1.0, 1.0, 1.0)
    mean, low, high = AbSummary._interval(np.array([0.0, 1.0] * 10))
    assert mean == 0.5
    assert low < 0.5 < high
