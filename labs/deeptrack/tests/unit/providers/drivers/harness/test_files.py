"""tests/unit/providers/drivers/harness/files: the agents directory read whole — every law refused with its name and file."""

from pathlib import Path

import pytest

from infra.config.providers import AGENTS
from infra.errors import HarnessError
from ports.harness import HarnessPort, Tier
from providers.drivers.harness.files import FilesDriver, Law
from tests.unit.providers.drivers.harness.conftest import Opened


async def test_files_meets_port() -> None:
    assert isinstance(FilesDriver(directory=AGENTS), HarnessPort)


async def test_files_loads_valid_roster(valid: Path, opened: Opened) -> None:
    roster = (await opened(valid)).roster
    assert sorted(roster.agents) == ["helper", "lead"]
    helper = roster.agents["helper"]
    assert (helper.spec.tier, helper.spec.tools, helper.spec.middleware) == (Tier.LOW, ("lookup",), ("audit",))
    assert (helper.instructions, [skill.name for skill in helper.skills]) == ("Help the lead.", ["glosario"])
    assert helper.skills[0].body == "Una póliza es un contrato."
    assert roster.context == "Dominio de prueba: pólizas y siniestros."
    assert roster.agents["lead"].spec.subagents == ("helper",)


async def test_files_versions_follow_content(tree: Path, opened: Opened) -> None:
    before = (await opened(tree)).roster
    (tree / "skills" / "glosario" / "SKILL.md").write_text(
        (tree / "skills" / "glosario" / "SKILL.md").read_text() + "Más.\n"
    )
    after = (await opened(tree)).roster
    assert before.agents["helper"].version != after.agents["helper"].version
    assert before.agents["lead"].version == after.agents["lead"].version
    assert len(after.agents["lead"].version) == 12


async def test_files_context_optional(tree: Path, opened: Opened) -> None:
    (tree / "CONTEXT.md").unlink()
    assert (await opened(tree)).roster.context == ""


async def test_files_main_roster_loads() -> None:
    async with FilesDriver(directory=AGENTS) as harness:
        assert {"insurance", "ontologo", "consultas", "transacciones"} <= set(harness.roster.agents)
        assert await harness.health()


@pytest.mark.parametrize(
    ("law", "file", "text"),
    [
        (Law.TREE, "missing", None),
        (Law.DECODE, "lead.md", "no frontmatter at all\n"),
        (Law.DECODE, "lead.md", "---\nname: lead\ndescription: x: y\n---\nbody\n"),
        (Law.DECODE, "lead.md", "---\nname: lead\ndescription: d\nmodel: gpt\n---\nbody\n"),
        (Law.DECODE, "lead.md", "---\nname: lead\ndescription: d\ntier: huge\n---\nbody\n"),
        (Law.NAME, "lead.md", "---\nname: chief\ndescription: d\nsubagents: [helper]\n---\nbody\n"),
        (Law.DESCRIBE, "lead.md", "---\nname: lead\ndescription: ''\nsubagents: [helper]\n---\nbody\n"),
        (Law.DESCRIBE, "lead.md", f"---\nname: lead\ndescription: {'x' * 1025}\nsubagents: [helper]\n---\nbody\n"),
        (Law.SKILL, "lead.md", "---\nname: lead\ndescription: d\nskills: [ghost]\nsubagents: [helper]\n---\nbody\n"),
        (Law.SKILL, "skills/glosario/SKILL.md", "---\nname: lexicon\ndescription: d\n---\nbody\n"),
        (Law.SUBAGENT, "lead.md", "---\nname: lead\ndescription: d\nsubagents: [ghost]\n---\nbody\n"),
        (Law.CYCLE, "helper.md", "---\nname: helper\ndescription: d\nsubagents: [lead]\n---\nbody\n"),
    ],
    ids=[
        "tree",
        "nofront",
        "yaml",
        "unknown",
        "tier",
        "name",
        "empty",
        "long",
        "skill",
        "skillname",
        "subagent",
        "cycle",
    ],
)
async def test_files_refuses(tree: Path, opened: Opened, law: Law, file: str, text: str | None) -> None:
    target = tree / "missing" if text is None else tree
    _ = text is not None and (tree / file).write_text(text)
    with pytest.raises(HarnessError) as refused:
        await opened(target)
    assert refused.value.law is law
    assert refused.value.path.endswith(file if text is not None else "missing")


async def test_files_roster_before_open() -> None:
    with pytest.raises(HarnessError) as refused:
        _ = FilesDriver(directory=AGENTS).roster
    assert refused.value.law is Law.OPEN


async def test_files_close(valid: Path, opened: Opened) -> None:
    driver = await opened(valid)
    await driver.__aexit__(None, None, None)
    assert not await driver.health()
