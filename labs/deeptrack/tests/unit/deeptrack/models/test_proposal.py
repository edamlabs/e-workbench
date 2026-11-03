"""Proposals decode only safe local names and render the Turtle the gate loads."""

from datetime import date

import msgspec
import pytest

from deeptrack.models.proposal import Denuncia, Endoso, Proposal


def test_proposal_turtle_denuncia() -> None:
    turtle = Denuncia(poliza="pol-1001", cobertura="cob-rc", fecha_ocurrencia=date(2026, 7, 1)).turtle
    assert 'seg:poliza seg:pol-1001 ; seg:cobertura seg:cob-rc ; seg:fechaOcurrencia "2026-07-01"^^xsd:date' in turtle


def test_proposal_turtle_endoso() -> None:
    assert "seg:endosa seg:pol-1001 ; seg:quita seg:cob-robo ." in Endoso(poliza="pol-1001", quita="cob-robo").turtle


@pytest.mark.parametrize(
    "name", ["pol-1001> . seg:x seg:y", "POL", "", "a" * 65], ids=["injection", "upper", "empty", "long"]
)
def test_proposal_rejects_unsafe_name(name: str) -> None:
    with pytest.raises(msgspec.ValidationError):
        msgspec.convert({"poliza": name, "quita": "cob-rc"}, Endoso)


def test_proposal_roundtrip_through_state() -> None:
    original = Denuncia(poliza="pol-1001", cobertura="cob-rc", fecha_ocurrencia=date(2026, 7, 1))
    assert msgspec.convert(msgspec.to_builtins(original), Proposal, strict=False) == original
