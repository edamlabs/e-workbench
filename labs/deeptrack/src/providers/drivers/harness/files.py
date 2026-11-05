"""providers/drivers/harness/files: FilesDriver — the agents directory read once, checked whole, at open.

The directory is data, outside the code (a volume in a container): one `<agent>.md` per agent — YAML frontmatter, the
spec; markdown body, the instructions —, shared skills in `skills/<skill>/SKILL.md`, and an optional `CONTEXT.md` every
agent shares. The frontmatter is decoded by e-serde into the strict `AgentSpec`. Opening applies the laws and refuses
the first breach with a `HarnessError` naming its law and file: TREE (the directory exists), DECODE (frontmatter
present and an `AgentSpec`), NAME (`name` is the file's stem), DESCRIBE (a description of 1 to 1024 characters),
SKILL (every skill named exists and names itself), SUBAGENT (every subagent named is an agent here), CYCLE (no agent
reaches itself through subagents). An agent's version is the digest of its file and of the skills it preloads."""

import asyncio
import graphlib
import hashlib
from enum import StrEnum, auto
from pathlib import Path
from typing import ClassVar, Final, Self

import eserde
import msgspec

from infra.errors import HarnessError
from infra.logger import logger
from ops.file import file_frontmatter
from ports.harness import Agent, AgentSpec, Roster, Skill
from ports.provider import Isolation, Locality, ProviderSpec, Workload

CONTEXT: Final[str] = "CONTEXT.md"
SKILLS: Final[str] = "skills"
SKILL: Final[str] = "SKILL.md"
DESCRIPTION: Final[int] = 1024
VERSION: Final[int] = 12


class Law(StrEnum):
    """The rules an agents directory must keep; a breach names one."""

    TREE = auto()
    DECODE = auto()
    NAME = auto()
    DESCRIBE = auto()
    SKILL = auto()
    SUBAGENT = auto()
    CYCLE = auto()
    OPEN = auto()


class SkillFront(msgspec.Struct, frozen=True, kw_only=True):
    """What etrack reads of a SKILL.md frontmatter; the standard's other fields (license, metadata…) pass untouched."""

    name: str
    description: str


class FilesDriver:
    """The roster of a directory: loaded off the loop at open, immutable after."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("files", Locality.FILESYSTEM, Workload.IO_BOUND, Isolation.THREAD)

    __slots__ = ("_directory", "_roster")

    def __init__(self, *, directory: Path) -> None:
        self._directory = directory
        self._roster: Roster | None = None

    ##### PRIVATE #####

    @property
    def _common_root(self) -> Path:
        return self._directory

    @staticmethod
    def _enter_split[T](path: Path, kind: type[T]) -> tuple[T, str, bytes]:
        raw = path.read_bytes()
        match file_frontmatter(raw.decode()):
            case None:
                raise HarnessError(Law.DECODE, str(path), "no `---` frontmatter block opens the file")
            case (front, body):
                try:
                    return eserde.loads(front.encode(), format=eserde.Format.YAML, type=kind), body, raw
                except eserde.LoaderError as failure:
                    raise HarnessError(Law.DECODE, str(path), str(failure)) from failure

    def _enter_skill(self, path: Path) -> tuple[Skill, str]:
        front, body, raw = self._enter_split(path, SkillFront)
        _ = front.name == path.parent.name or self._enter_refuse(Law.SKILL, path, f"names itself {front.name!r}")
        return Skill(name=front.name, description=front.description, body=body), hashlib.sha256(raw).hexdigest()

    def _enter_agent(self, path: Path, skills: dict[str, tuple[Skill, str]]) -> Agent:
        spec, body, raw = self._enter_split(path, AgentSpec)
        _ = spec.name == path.stem or self._enter_refuse(
            Law.NAME, path, f"declares {spec.name!r}, the file says {path.stem!r}"
        )
        _ = 0 < len(spec.description) <= DESCRIPTION or self._enter_refuse(
            Law.DESCRIBE, path, f"1 to {DESCRIPTION} characters"
        )
        missing = sorted(set(spec.skills) - set(skills))
        _ = missing and self._enter_refuse(Law.SKILL, path, f"names skills that do not exist: {missing}")
        digest = hashlib.sha256(raw + b"".join(skills[name][1].encode() for name in spec.skills)).hexdigest()
        return Agent(
            spec=spec,
            instructions=body,
            skills=tuple(skills[name][0] for name in spec.skills),
            version=digest[:VERSION],
        )

    def _enter_graph(self, agents: dict[str, Agent]) -> None:
        root = self._common_root
        unknown = sorted(
            (name, each) for name, agent in agents.items() for each in agent.spec.subagents if each not in agents
        )
        _ = unknown and self._enter_refuse(
            Law.SUBAGENT, root / f"{unknown[0][0]}.md", f"names agents that do not exist: {unknown}"
        )
        try:
            graphlib.TopologicalSorter({name: agent.spec.subagents for name, agent in agents.items()}).prepare()
        except graphlib.CycleError as failure:
            loop: list[str] = failure.args[1]
            raise HarnessError(
                Law.CYCLE, str(root / f"{loop[0]}.md"), f"subagents loop: {' → '.join(loop)}"
            ) from failure

    def _enter_load(self) -> Roster:
        root = self._common_root
        _ = root.is_dir() or self._enter_refuse(Law.TREE, root, "is not a directory")
        skills = {path.parent.name: self._enter_skill(path) for path in sorted((root / SKILLS).glob(f"*/{SKILL}"))}
        agents = {
            path.stem: self._enter_agent(path, skills) for path in sorted(root.glob("*.md")) if path.name != CONTEXT
        }
        self._enter_graph(agents)
        context = (root / CONTEXT).read_text().strip("\n") if (root / CONTEXT).is_file() else ""
        return Roster(agents=agents, context=context)

    @staticmethod
    def _enter_refuse(law: Law, path: Path, message: str) -> None:
        raise HarnessError(law, str(path), message)

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        ### reading and hashing a directory is blocking I/O: off the loop, once, before anything is served.
        self._roster = await asyncio.to_thread(self._enter_load)
        versions = {name: agent.version for name, agent in self._roster.agents.items()}
        logger.info("harness open", driver="files", directory=str(self._common_root), agents=versions)
        return self

    async def __aexit__(self, *exc: object) -> None:
        self._roster = None
        logger.info("harness closed", driver="files")

    async def health(self) -> bool:
        """Open: the roster was loaded and passed every law."""
        return self._roster is not None

    @property
    def roster(self) -> Roster:
        """The checked roster; reading it before open is the caller's bug."""
        match self._roster:
            case None:
                raise HarnessError(Law.OPEN, str(self._common_root), "the harness is not open: the lifespan opens it")
            case roster:
                return roster
