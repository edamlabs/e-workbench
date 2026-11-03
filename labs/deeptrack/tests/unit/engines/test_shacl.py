"""A validation round: clear, reload the base, add the candidate, judge — and a report that is not one."""

import pytest

from engines.shacl import ShaclEngine
from infra.errors import ShaclError
from tests.support.fake import FakeOntology


async def test_shacl_round_order() -> None:
    server = FakeOntology([True])
    report = await ShaclEngine(server, base=("schema", "data"), shapes="shapes").validate("candidate")
    assert report.conforms
    assert server.calls == [
        ("onto_clear", {}),
        ("onto_load", {"turtle": "schema"}),
        ("onto_load", {"turtle": "data"}),
        ("onto_load", {"turtle": "candidate"}),
        ("onto_shacl", {"shapes": "shapes", "inline": True}),
    ]


async def test_shacl_violation_text() -> None:
    report = await ShaclEngine(FakeOntology([False]), base=(), shapes="s").validate("c")
    assert report.text == "- fuera de vigencia (seg:propuesta)"


async def test_shacl_rejects_foreign_report() -> None:
    class Broken(FakeOntology):
        async def call(self, tool, args, config=None):
            return "not json"

    with pytest.raises(ShaclError):
        await ShaclEngine(Broken(), base=(), shapes="s").validate("c")
