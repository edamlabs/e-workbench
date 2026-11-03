"""ShaclEngine on the real validation server: every bench case's proposal, judged as the shapes say."""

from datetime import date

import pytest

from deeptrack.models.proposal import Denuncia, Endoso, Proposal
from engines.shacl import ShaclEngine
from infra.settings import settings as st
from providers.drivers.ontology.openontologies import OpenOntologiesDriver

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ("proposal", "violation"),
    [
        (Denuncia(poliza="pol-1001", cobertura="cob-rc", fecha_ocurrencia=date(2026, 7, 1)), None),
        (Endoso(poliza="pol-1001", quita="cob-rc"), None),
        (Denuncia(poliza="pol-2002", cobertura="cob-incendio", fecha_ocurrencia=date(2026, 7, 1)), "vigencia"),
        (Denuncia(poliza="pol-1001", cobertura="cob-robo", fecha_ocurrencia=date(2025, 12, 15)), "vigencia"),
        (Endoso(poliza="pol-1001", quita="cob-robo"), "siniestro abierto"),
        (
            Denuncia(poliza="pol-1001", cobertura="cob-incendio", fecha_ocurrencia=date(2026, 7, 1)),
            "no está contratada",
        ),
        (Denuncia(poliza="pol-9999", cobertura="cob-rc", fecha_ocurrencia=date(2026, 7, 1)), "póliza existente"),
    ],
    ids=["valid-claim", "valid-endorsement", "out-of-term", "before-term", "open-claim", "not-covered", "no-policy"],
)
async def test_shacl_judges_bench_cases(proposal: Proposal, violation: str | None) -> None:
    servers = st.providers.drivers.ontology.openontologies
    async with OpenOntologiesDriver(servers.val_url) as server:
        report = await ShaclEngine(server, base=st.ontology.texts, shapes=st.ontology.shapes_text).validate(
            proposal.turtle
        )
    assert report.conforms is (violation is None)
    assert violation is None or any(violation in each.message for each in report.violations)
