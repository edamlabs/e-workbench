"""tests/unit/ports/harness: the roster's one operation — agents removed whole, and from every list that named them."""

from tests.support.agents import ROSTER


async def test_roster_without_drops_agent_and_references() -> None:
    kept = ROSTER.without("ontologo")
    assert "ontologo" not in kept.agents
    assert kept.agents["insurance"].spec.subagents == ("consultas", "transacciones")
    assert ROSTER.agents["insurance"].spec.subagents == ("ontologo", "consultas", "transacciones")
