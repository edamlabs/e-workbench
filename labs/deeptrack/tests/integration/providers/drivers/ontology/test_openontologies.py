"""OpenOntologiesDriver against the lab's two servers: whitelists, refusal, health, an unreachable server."""

import pytest

from infra.errors import OntologyError
from infra.settings import settings as st
from providers.drivers.ontology.openontologies import OpenOntologiesDriver

pytestmark = pytest.mark.integration
SERVERS = st.providers.drivers.ontology.openontologies


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
        answer = await reference.call("onto_query", {"query": "ASK { <https://deeptrack.lab/seguros#pol-1001> ?p ?o }"})
    assert "true" in answer.lower()


async def test_openontologies_unreachable() -> None:
    with pytest.raises(OntologyError, match="cannot open a session"):
        async with OpenOntologiesDriver("http://localhost:28199/mcp"):
            pass
