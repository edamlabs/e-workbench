"""The prevalidate arm on the real model: the ontology judges inside the proposing tool, before the gate."""

import time

import pytest
from etrack.models.event import EventPhase

from infra.lifespan.sealed import lifespan
from models.arm import Arm
from tests.support.track import record

pytestmark = [pytest.mark.integration, pytest.mark.llm]


async def test_arm_prevalidate_stops_inside_the_loop() -> None:
    async with lifespan() as state:
        chat = state.services.arms.chat(Arm.PREVALIDATE)
        recorder = record(state.providers.track.bus)
        turn = await chat.turn(f"arm-{time.time_ns()}", "Quita la cobertura de robo total de la póliza pol-1001")
        frames = await recorder.settled(turn.run_id)
    assert turn.interrupt is None
    shacl = [f for f in frames if f.name == "onto_shacl" and f.phase is EventPhase.END]
    ### the shapes judged under the proposing tool (in its loop), never in the gate node: no proposal ever landed.
    assert shacl
    assert all(f.node != "gate" for f in shacl)


async def test_arm_prevalidate_lets_valid_through() -> None:
    async with lifespan() as state:
        chat = state.services.arms.chat(Arm.PREVALIDATE)
        turn = await chat.turn(
            f"arm-{time.time_ns()}", "Quita la cobertura de responsabilidad civil de la póliza pol-1001"
        )
    assert turn.interrupt == {"propuesta": {"type": "endoso", "poliza": "pol-1001", "quita": "cob-rc"}}
