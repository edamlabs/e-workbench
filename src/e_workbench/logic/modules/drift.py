"""M7 · drift: the project declares what the fleet says it is.

Every EDamLabs repository states its identity in its manifest: `pyproject.toml` `[tool.edamlabs]`, or for a Rust
project `Cargo.toml` `[package.metadata.edamlabs]` (`[workspace.metadata.edamlabs]` in a workspace): `kind` (what it
ships) and `family` (what it is). A missing declaration is a deterministic fix; a declaration that contradicts the fleet entry
is a human's call, since either side may be the wrong one.

The repository's public face (GitHub's About) says what the manifest says: the description equals the manifest's,
the topics hold every keyword (an eager project also `eager-stack`), the homepage is the documentation URL when one
is declared. The manifest is the source of truth: a face that differs is a deterministic fix, given as the exact
`gh repo edit` to run; a manifest without description or keywords is the manifest's fix first.
"""

import asyncio
import re
import tomllib
from collections.abc import Callable, Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final

from e_workbench.logic.ports import HostPort
from e_workbench.models.fleet import FamilyFleet, Fleet
from e_workbench.models.report import FindingReport, Report
from e_workbench.models.signal import RepositorySignal
from e_workbench.models.verdict import Verdict

MODULE: Final = "drift"
FIELDS: Final = ("kind", "family")
### Manifest → where its EDamLabs table lives; the first manifest declaring one wins, in this order.
MANIFESTS: Final[Mapping[str, tuple[str, Callable[[dict[str, Any]], dict[str, Any]]]]] = MappingProxyType(
    {
        "pyproject.toml": ("pyproject.toml [tool.edamlabs]", lambda doc: doc.get("tool", {}).get("edamlabs", {})),
        "Cargo.toml": (
            "Cargo.toml [package.metadata.edamlabs]",
            lambda doc: (
                doc.get("package", {}).get("metadata", {}).get("edamlabs")
                or doc.get("workspace", {}).get("metadata", {}).get("edamlabs")
                or {}
            ),
        ),
    }
)


### Manifest → where its public identity lives, and how to read description, keywords and documentation URL from it.
ABOUT: Final[Mapping[str, tuple[str, Callable[[dict[str, Any]], tuple[str, tuple[str, ...], str]]]]] = MappingProxyType(
    {
        "pyproject.toml": (
            "pyproject.toml [project]",
            lambda doc: (
                doc.get("project", {}).get("description", ""),
                tuple(doc.get("project", {}).get("keywords", ())),
                doc.get("project", {}).get("urls", {}).get("Documentation", ""),
            ),
        ),
        "Cargo.toml": (
            "Cargo.toml [package] (a workspace: [workspace.package])",
            lambda doc: (
                (package := doc.get("package") or doc.get("workspace", {}).get("package", {})).get("description", ""),
                tuple(package.get("keywords", ())),
                package.get("documentation", ""),
            ),
        ),
    }
)
### GitHub's topic law: lowercase letters, digits and hyphens, 50 characters at most.
NOT_TOPIC: Final = re.compile(r"[^a-z0-9-]+")
FAMILY_TOPICS: Final[Mapping[FamilyFleet, frozenset[str]]] = MappingProxyType(
    {FamilyFleet.EAGER: frozenset({"eager-stack"}), FamilyFleet.BINDING: frozenset(), FamilyFleet.INFRA: frozenset()}
)


class DriftModule:
    """Identity drift of one fleet entry: `[tool.edamlabs]` against the fleet."""

    __slots__ = ("_host", "_now")

    def __init__(self, host: HostPort, now: datetime) -> None:
        self._host = host
        self._now = now

    ##### PRIVATE #####

    async def _run_manifests(self, repo: str) -> dict[str, dict[str, Any]]:
        """Every manifest the repository has, parsed, by file name, in the order the tables are looked for."""
        texts = await asyncio.gather(*(self._host.file(repo, name) for name in MANIFESTS))
        return {name: tomllib.loads(text) for name, text in zip(MANIFESTS, texts, strict=True) if text is not None}

    @staticmethod
    def _run_declared(docs: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        """Where the identity is (or should be) declared, and the declared table; empty when none declares it."""
        found = [(MANIFESTS[name][0], MANIFESTS[name][1](doc)) for name, doc in docs.items()]
        default = (found[0][0], {}) if found else (MANIFESTS["pyproject.toml"][0], {})
        return next((entry for entry in found if entry[1]), default)

    @staticmethod
    def _run_finding(field: str, declared: object, expected: str, where: str) -> FindingReport:
        """One identity field: equal is OK, absent is a fix to make, different is a contradiction to settle."""
        match declared:
            case value if value == expected:
                verdict, detail = Verdict.OK, f"{field} = {expected}"
            case None:
                verdict, detail = Verdict.ACT, f'declare `{field} = "{expected}"` in {where}'
            case value:
                verdict, detail = Verdict.ESCALATE, f"{where} says {field} = {value!r}, the fleet says {expected!r}"
        return FindingReport(
            key=f"{MODULE}:identity:{field}",
            module=MODULE,
            subject="identity",
            check=field,
            verdict=verdict,
            detail=detail,
        )

    @staticmethod
    def _about_finding(check: str, verdict: Verdict, detail: str) -> FindingReport:
        return FindingReport(
            key=f"{MODULE}:about:{check}", module=MODULE, subject="about", check=check, verdict=verdict, detail=detail
        )

    @staticmethod
    def _about_topic(keyword: str) -> str:
        """A manifest keyword as a GitHub topic."""
        return NOT_TOPIC.sub("-", keyword.lower().replace(" ", "-")).strip("-")[:50]

    def _run_about(
        self, fleet: Fleet, docs: dict[str, dict[str, Any]], face: RepositorySignal | None
    ) -> tuple[FindingReport, ...]:
        """The public face against the manifest: description, topics and homepage, each with the fix that aligns it."""
        declared = [(ABOUT[name][0], ABOUT[name][1](doc)) for name, doc in docs.items()]
        where, (description, keywords, docs_url) = next(
            (entry for entry in declared if entry[1][0]),
            declared[0] if declared else (ABOUT["pyproject.toml"][0], ("", (), "")),
        )
        match face:
            case None:
                return (self._about_finding("repository", Verdict.ESCALATE, f"{fleet.repo} is not on the host"),)
            case _:
                pass
        edit = f"gh repo edit {fleet.repo}"
        expected = {self._about_topic(keyword) for keyword in keywords} - {""} | FAMILY_TOPICS[fleet.family]
        return (
            self._about_description(edit, where, description, face.description),
            self._about_topics(edit, where, keywords, expected, face.topics),
            self._about_homepage(edit, docs_url, face.homepage),
        )

    @classmethod
    def _about_description(cls, edit: str, where: str, wanted: str, shown: str) -> FindingReport:
        match wanted:
            case "":
                return cls._about_finding("description", Verdict.ESCALATE, f"declare `description` in {where}")
            case _ if shown == wanted:
                return cls._about_finding("description", Verdict.OK, wanted)
            case _:
                return cls._about_finding("description", Verdict.ACT, f'{edit} --description "{wanted}"')

    @classmethod
    def _about_topics(
        cls, edit: str, where: str, keywords: tuple[str, ...], expected: set[str], shown: tuple[str, ...]
    ) -> FindingReport:
        missing = sorted(expected - set(shown))
        match keywords, missing:
            case (), _:
                return cls._about_finding("topics", Verdict.ESCALATE, f"declare `keywords` in {where}")
            case _, []:
                return cls._about_finding("topics", Verdict.OK, ",".join(sorted(expected)))
            case _:
                return cls._about_finding("topics", Verdict.ACT, f"{edit} --add-topic {','.join(missing)}")

    @classmethod
    def _about_homepage(cls, edit: str, wanted: str, shown: str) -> FindingReport:
        match wanted:
            case "":
                return cls._about_finding("homepage", Verdict.OK, shown or "no documentation URL declared")
            case _ if shown == wanted:
                return cls._about_finding("homepage", Verdict.OK, wanted)
            case _:
                return cls._about_finding("homepage", Verdict.ACT, f"{edit} --homepage {wanted}")

    ############################################################

    ##### PUBLIC #####

    async def run(self, fleet: Fleet) -> Report:
        """The drift report of a fleet entry: one finding per identity field, then the public face's three."""
        docs, face = await asyncio.gather(self._run_manifests(fleet.repo), self._host.repository(fleet.repo))
        where, declared = self._run_declared(docs)
        expected = {"kind": str(fleet.kind), "family": str(fleet.family)}
        identity = tuple(self._run_finding(field, declared.get(field), expected[field], where) for field in FIELDS)
        return Report(
            repo=fleet.repo,
            module=MODULE,
            generated=self._now,
            findings=(*identity, *self._run_about(fleet, docs, face)),
        )
