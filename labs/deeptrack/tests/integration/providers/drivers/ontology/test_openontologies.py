"""OpenOntologiesDriver against the lab's two servers: whitelists, refusal, health, unreachable, restarted."""

import pytest

from infra.errors import OntologyError
from infra.settings import Settings
from infra.settings import settings as st
from providers.drivers.ontology.openontologies import OpenOntologiesDriver
from tests.integration.providers.drivers.ontology.conftest import Restart

pytestmark = pytest.mark.integration


async def test_openontologies_whitelists(servers: Settings) -> None:
    async with (
        OpenOntologiesDriver(servers.onto_ref_url) as reference,
        OpenOntologiesDriver(servers.onto_val_url) as validation,
    ):
        assert sorted(reference.tools) == ["onto_load", "onto_query", "onto_stats"]
        assert sorted(validation.tools) == ["onto_clear", "onto_load", "onto_shacl", "onto_stats"]
        assert await reference.health()


async def test_openontologies_refuses_unadvertised(servers: Settings) -> None:
    async with OpenOntologiesDriver(servers.onto_ref_url) as reference:
        with pytest.raises(OntologyError, match="not advertised"):
            await reference.call("onto_clear", {})


async def test_openontologies_seed_is_queryable(servers: Settings, ask: str) -> None:
    async with OpenOntologiesDriver(servers.onto_ref_url, seed=st.ontology_texts) as reference:
        answer = await reference.call("onto_query", {"query": ask})
    assert "true" in answer.lower()


async def test_openontologies_unreachable() -> None:
    with pytest.raises(OntologyError, match="cannot open a session"):
        async with OpenOntologiesDriver("http://localhost:28199/mcp"):
            pass


async def test_openontologies_reconnects_and_reseeds(servers: Settings, ask: str, restart: Restart) -> None:
    async with OpenOntologiesDriver(servers.onto_ref_url, seed=st.ontology_texts) as reference:
        await restart("labs-ontoref")
        answer = await reference.call("onto_query", {"query": ask})
    assert "true" in answer.lower()


async def test_openontologies_refuses_replay_of_writes(servers: Settings, restart: Restart) -> None:
    async with OpenOntologiesDriver(servers.onto_val_url) as validation:
        await restart("labs-ontoval")
        with pytest.raises(OntologyError, match="lost during onto_load"):
            await validation.call("onto_load", {"turtle": st.ontology_texts[0]})
        assert await validation.health()


async def test_openontologies_agent_tool_reports_failure(servers: Settings, ask: str, restart: Restart) -> None:
    async with OpenOntologiesDriver(servers.onto_ref_url, seed=st.ontology_texts) as reference:
        await restart("labs-ontoref")
        answer = await reference.tools["onto_load"].ainvoke({"turtle": st.ontology_texts[0]})
        assert "lost during onto_load" in str(answer)
        assert "true" in (await reference.call("onto_query", {"query": ask})).lower()
