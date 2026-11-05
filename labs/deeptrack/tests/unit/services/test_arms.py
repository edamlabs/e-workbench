"""tests/unit/services/arms: the real roster resolved against this system — roles hold their tools only."""

from models.arm import Arm
from services.arms import ENTRY
from tests.support.agents import arms
from tests.support.fake import ToolOntology, script
from tests.unit.services.conftest import Roles


async def test_arms_roles_hold_their_tools_only(roles: Roles) -> None:
    held = {name: sorted(tool.name for tool in spec["tools"]) for name, spec in roles(True).items()}
    assert held == {
        "ontologo": ["onto_query", "onto_stats"],
        "consultas": ["consultar_poliza"],
        "transacciones": ["consultar_poliza"],
    }


async def test_arms_transacciones_proposes_through_middleware(roles: Roles) -> None:
    (proposing,) = roles(True)["transacciones"]["middleware"]
    assert sorted(tool.name for tool in proposing.tools) == ["proponer_denuncia", "proponer_endoso"]


async def test_arms_without_ontologist_drops_the_role(roles: Roles) -> None:
    assert sorted(roles(False)) == ["consultas", "transacciones"]


async def test_arms_agent_builds_the_entry(server: ToolOntology) -> None:
    assert arms(script(), server).agent(Arm.NO_ONTOLOGIST).name == ENTRY
