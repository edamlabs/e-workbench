"""OpenOntologiesDriver against the lab's two servers: whitelists, refusal, health, unreachable, restarted."""

import asyncio

import pytest

from infra.errors import OntologyError
from infra.settings import settings as st
from providers.drivers.ontology.openontologies import OpenOntologiesDriver

pytestmark = pytest.mark.integration
SERVERS = st.providers.drivers.ontology.openontologies
ASK = "ASK { <https://deeptrack.lab/seguros#pol-1001> ?p ?o }"


async def test_openontologies_whitelists() -> None:
    async with OpenOntologiesDriver(SERVERS.ref_url) as reference, OpenOntologiesDriver(SERVERS.val_url) as validation:
        assert sorted(reference.tools) == ["onto_load", "onto_query", "onto_stats"]
        assert sorted(validation.tools) == ["onto_clear", "onto_load", "onto_shacl", "onto_stats"]
        assert await reference.health()


async def test_openontologies_refuses_unadvertised() -> None:
    async with OpenOntologiesDriver(SERVERS.ref_url) as reference:
        with pytest.raises(OntologyError, match="not advertised"):
            await reference.call("onto_clear", {})


async def test_openontologies_seed_is_queryable() -> None:
    async with OpenOntologiesDriver(SERVERS.ref_url, seed=st.ontology.texts) as reference:
        answer = await reference.call("onto_query", {"query": ASK})
    assert "true" in answer.lower()


async def test_openontologies_unreachable() -> None:
    with pytest.raises(OntologyError, match="cannot open a session"):
        async with OpenOntologiesDriver("http://localhost:28199/mcp"):
            pass


async def restart(container: str) -> None:
    """Restart one of the lab's containers and wait until its MCP endpoint answers again."""
    process = await asyncio.create_subprocess_exec("docker", "restart", container, stdout=asyncio.subprocess.DEVNULL)
    await process.wait()
    await asyncio.sleep(2)


async def test_openontologies_reconnects_and_reseeds() -> None:
    async with OpenOntologiesDriver(SERVERS.ref_url, seed=st.ontology.texts) as reference:
        await restart("labs-ontoref")
        answer = await reference.call("onto_query", {"query": ASK})
    assert "true" in answer.lower()


async def test_openontologies_refuses_replay_of_writes() -> None:
    async with OpenOntologiesDriver(SERVERS.val_url) as validation:
        await restart("labs-ontoval")
        with pytest.raises(OntologyError, match="lost during onto_load"):
            await validation.call("onto_load", {"turtle": st.ontology.texts[0]})
        assert await validation.health()


async def test_openontologies_agent_tool_reports_failure() -> None:
    async with OpenOntologiesDriver(SERVERS.ref_url, seed=st.ontology.texts) as reference:
        await restart("labs-ontoref")
        answer = await reference.tools["onto_load"].ainvoke({"turtle": st.ontology.texts[0]})
        assert "lost during onto_load" in str(answer)
        assert "true" in (await reference.call("onto_query", {"query": ASK})).lower()
