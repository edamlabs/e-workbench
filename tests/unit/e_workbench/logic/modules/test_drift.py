"""M7 · drift: `[tool.edamlabs]` declares what the fleet says the project is."""

import msgspec
import pytest

from e_workbench.logic.modules.drift import DriftModule
from e_workbench.models.fleet import FamilyFleet, Fleet
from e_workbench.models.signal import RepositorySignal
from e_workbench.models.verdict import Verdict
from tests.unit.e_workbench.logic.conftest import FakeHost


@pytest.mark.parametrize(
    ("manifest", "expected"),
    [
        ('[tool.edamlabs]\nkind = "lib"\nfamily = "binding"\n', {"kind": Verdict.OK, "family": Verdict.OK}),
        ('[tool.edamlabs]\nkind = "lib"\n', {"kind": Verdict.OK, "family": Verdict.ACT}),
        (
            '[tool.edamlabs]\nkind = "service"\nfamily = "eager"\n',
            {"kind": Verdict.ESCALATE, "family": Verdict.ESCALATE},
        ),
        ('[project]\nname = "x"\n', {"kind": Verdict.ACT, "family": Verdict.ACT}),
        (None, {"kind": Verdict.ACT, "family": Verdict.ACT}),
    ],
    ids=["declared", "family-missing", "contradicted", "no-table", "no-manifest"],
)
async def test_run_identity(
    host: FakeHost, drift_module: DriftModule, fleet: Fleet, manifest: str | None, expected: dict[str, Verdict]
) -> None:
    host.files |= {("edamlabs/project", "pyproject.toml"): manifest} if manifest is not None else {}
    report = await drift_module.run(fleet)
    assert {f.check: f.verdict for f in report.findings if f.subject == "identity"} == expected


@pytest.mark.parametrize(
    ("files", "expected", "where"),
    [
        ({"Cargo.toml": '[package.metadata.edamlabs]\nkind = "lib"\nfamily = "binding"\n'}, Verdict.OK, "Cargo.toml"),
        ({"Cargo.toml": '[workspace.metadata.edamlabs]\nkind = "lib"\nfamily = "binding"\n'}, Verdict.OK, "Cargo.toml"),
        (
            {
                "pyproject.toml": '[project]\nname = "x"\n',
                "Cargo.toml": '[package.metadata.edamlabs]\nkind = "lib"\nfamily = "binding"\n',
            },
            Verdict.OK,
            "Cargo.toml",
        ),
        ({"Cargo.toml": '[package]\nname = "x"\n'}, Verdict.ACT, "Cargo.toml [package.metadata.edamlabs]"),
    ],
    ids=["cargo-package", "cargo-workspace", "pyproject-without-table-yields", "cargo-without-table"],
)
async def test_run_identity_cargo(
    host: FakeHost, drift_module: DriftModule, fleet: Fleet, files: dict[str, str], expected: Verdict, where: str
) -> None:
    host.files |= {("edamlabs/project", name): text for name, text in files.items()}
    report = await drift_module.run(fleet)
    assert {f.verdict for f in report.findings if f.subject == "identity"} == {expected}
    assert all(where in f.detail for f in report.findings if f.verdict is Verdict.ACT)


@pytest.mark.parametrize(
    ("face", "expected"),
    [
        (
            RepositorySignal(
                "edamlabs/project",
                False,
                None,
                description="Fast codecs.",
                topics=("python", "yaml"),
                homepage="https://docs",
            ),
            {"description": Verdict.OK, "topics": Verdict.OK, "homepage": Verdict.OK},
        ),
        (
            RepositorySignal("edamlabs/project", False, None),
            {"description": Verdict.ACT, "topics": Verdict.ACT, "homepage": Verdict.ACT},
        ),
    ],
    ids=["aligned", "empty-face"],
)
async def test_run_about(
    host: FakeHost, drift_module: DriftModule, fleet: Fleet, face: RepositorySignal, expected: dict[str, Verdict]
) -> None:
    manifest = '[project]\nname = "x"\ndescription = "Fast codecs."\nkeywords = ["Python", "YAML"]\n[project.urls]\nDocumentation = "https://docs"\n'
    host.files |= {("edamlabs/project", "pyproject.toml"): manifest}
    host.repositories |= {"edamlabs/project": face}
    report = await drift_module.run(fleet)
    about = {f.check: f for f in report.findings if f.subject == "about"}
    assert {check: finding.verdict for check, finding in about.items()} == expected
    assert all(f.detail.startswith("gh repo edit edamlabs/project") for f in about.values() if f.verdict is Verdict.ACT)


async def test_run_about_eager_topic_and_cargo(host: FakeHost, drift_module: DriftModule, fleet: Fleet) -> None:
    manifest = '[package]\nname = "x"\ndescription = "Speech."\nkeywords = ["tts"]\n'
    host.files |= {("edamlabs/project", "Cargo.toml"): manifest}
    host.repositories |= {
        "edamlabs/project": RepositorySignal("edamlabs/project", False, None, description="Speech.", topics=("tts",))
    }
    eager = msgspec.structs.replace(fleet, family=FamilyFleet.EAGER)
    about = {f.check: f for f in (await drift_module.run(eager)).findings if f.subject == "about"}
    assert (about["topics"].verdict, about["topics"].detail) == (
        Verdict.ACT,
        "gh repo edit edamlabs/project --add-topic eager-stack",
    )
    assert about["homepage"].verdict is Verdict.OK


@pytest.mark.parametrize(
    ("manifest", "face"),
    [('[project]\nname = "x"\n', RepositorySignal("edamlabs/project", False, None)), (None, None)],
    ids=["undeclared", "no-repository"],
)
async def test_run_about_escalates(
    host: FakeHost, drift_module: DriftModule, fleet: Fleet, manifest: str | None, face: RepositorySignal | None
) -> None:
    host.files |= {("edamlabs/project", "pyproject.toml"): manifest} if manifest else {}
    host.repositories |= {"edamlabs/project": face} if face else {}
    about = [f for f in (await drift_module.run(fleet)).findings if f.subject == "about"]
    assert Verdict.ESCALATE in {f.verdict for f in about}


async def test_run_about_cargo_workspace(host: FakeHost, drift_module: DriftModule, fleet: Fleet) -> None:
    manifest = '[workspace]\nmembers = []\n[workspace.package]\ndescription = "Speech."\nkeywords = ["tts"]\n'
    host.files |= {("edamlabs/project", "Cargo.toml"): manifest}
    host.repositories |= {
        "edamlabs/project": RepositorySignal("edamlabs/project", False, None, description="Speech.", topics=("tts",))
    }
    about = {f.check: f.verdict for f in (await drift_module.run(fleet)).findings if f.subject == "about"}
    assert about == {"description": Verdict.OK, "topics": Verdict.OK, "homepage": Verdict.OK}
