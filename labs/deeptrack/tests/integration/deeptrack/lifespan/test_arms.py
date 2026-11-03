"""The prevalidate arm on the real model: the ontology judges inside the proposing tool, before the gate."""

import time

import pytest

from deeptrack.lifespan import engines, services
from deeptrack.lifespan.sealed import lifespan
from deeptrack.models.arm import Arm
from processors.models import EventPhase, RunEvent

pytestmark = [pytest.mark.integration, pytest.mark.llm]


async def test_arm_prevalidate_stops_inside_the_loop() -> None:
    frames: list[RunEvent] = []
    async with lifespan() as state:
        mounted = state.providers
        chat = services.chat(mounted, engines.built(mounted, Arm.PREVALIDATE), Arm.PREVALIDATE)
        turn = await chat.turn(
            f"arm-{time.time_ns()}", "Quita la cobertura de robo total de la póliza pol-1001", frames.append
        )
    assert turn.interrupt is None
    shacl = [f for f in frames if f.name == "onto_shacl" and f.phase is EventPhase.END]
    ### the shapes judged under the proposing tool (in its loop), never in the gate node: no proposal ever landed.
    assert shacl
    assert all(f.node != "gate" for f in shacl)


async def test_arm_prevalidate_lets_valid_through() -> None:
    async with lifespan() as state:
        mounted = state.providers
        chat = services.chat(mounted, engines.built(mounted, Arm.PREVALIDATE), Arm.PREVALIDATE)
        turn = await chat.turn(
            f"arm-{time.time_ns()}", "Quita la cobertura de responsabilidad civil de la póliza pol-1001", lambda _: None
        )
    assert turn.interrupt == {"propuesta": {"type": "endoso", "poliza": "pol-1001", "quita": "cob-rc"}}
