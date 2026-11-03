"""tests/unit/test_taxonomy: the import table, the framework fence and the shape of every provider, read on the tree.

Imports are read with `ast` (tach holds the layers too; this is the second, readable gate). The core — models, ports,
processors (layout aside), logic — never names a framework: each foreign library enters through the one module that
owns it. Every class that names itself a driver or an adapter declares its spec and lifecycle, lives at
`providers/<nature>/<capability>/<name>.py` where `<capability>` is a module of `ports/`, meets that port, agrees
with its locality (`EMBEDDED` is an adapter) and carries a unique `<Name><Nature>` name. Config mirrors the tree."""

import ast
import importlib
from collections import Counter
from pathlib import Path
from typing import Final, get_protocol_members

import pytest

from etrack.infra.config.base import BaseSettings
from etrack.ports.provider import Locality, Provider, ProviderSpec

PACKAGE: Final = Path(__file__).resolve().parents[2] / "src" / "etrack"
FORBIDDEN: Final[dict[str, frozenset[str]]] = {
    "models": frozenset({"ports", "providers", "processors", "logic", "infra"}),
    "ports": frozenset({"providers", "processors", "logic"}),
    "providers/drivers": frozenset({"providers", "processors", "logic"}),
    "providers/adapters": frozenset({"providers", "processors", "logic"}),
    "processors": frozenset({"providers", "logic"}),
    "logic": frozenset({"providers"}),
    "infra": frozenset({"ports", "providers", "processors", "logic", "models"}),
    "ops": frozenset({"ports", "providers", "processors", "logic", "models"}),
}
FRAMEWORKS: Final[dict[str, frozenset[str]]] = {
    "langchain_core": frozenset({"providers/adapters/source/langgraph.py"}),
    "langgraph": frozenset({"providers/adapters/source/langgraph.py", "providers/adapters/topology/langgraph.py"}),
    "opentelemetry": frozenset({"providers/drivers/sink/otlp.py"}),
    "rustworkx": frozenset({"processors/layout.py"}),
    "eserde": frozenset({"providers/drivers/sink/otlp.py"}),
}
LIFECYCLE: Final = ("__aenter__", "__aexit__", "health")


def _modules(folder: str) -> list[Path]:
    return sorted(path for path in (PACKAGE / folder).rglob("*.py") if "__pycache__" not in path.parts)


def _dotted(path: Path) -> str:
    return "etrack." + path.relative_to(PACKAGE).with_suffix("").as_posix().replace("/", ".")


def _names(path: Path) -> set[str]:
    nodes = list(ast.walk(ast.parse(path.read_text("utf-8"))))
    named = {node.module for node in nodes if isinstance(node, ast.ImportFrom) and node.module}
    return named | {alias.name for node in nodes if isinstance(node, ast.Import) for alias in node.names}


def _layers(path: Path) -> set[str]:
    return {name.split(".")[1] for name in _names(path) if name.startswith("etrack.")}


##### THE IMPORT TABLE #####
CASES: Final = [(folder, path) for folder in FORBIDDEN for path in _modules(folder)]


@pytest.mark.parametrize(
    ("folder", "path"), CASES, ids=[f"{folder}:{path.relative_to(PACKAGE)}" for folder, path in CASES]
)
async def test_taxonomy_imports_obey_the_table(folder: str, path: Path) -> None:
    breaking = _layers(path) & FORBIDDEN[folder]
    assert not breaking, f"{path.relative_to(PACKAGE)} imports {sorted(breaking)}, which a {folder} module may not"


##### THE FRAMEWORK FENCE #####
EVERY: Final = _modules(".")


@pytest.mark.parametrize("path", EVERY, ids=[str(path.relative_to(PACKAGE)) for path in EVERY])
async def test_taxonomy_frameworks_enter_through_their_module(path: Path) -> None:
    relative = path.relative_to(PACKAGE).as_posix()
    spoken = {root for root in FRAMEWORKS for name in _names(path) if name == root or name.startswith(f"{root}.")}
    trespassing = {root for root in spoken if relative not in FRAMEWORKS[root]}
    assert not trespassing, f"{relative} speaks {sorted(trespassing)}: only its owning module may"


##### PROVIDERS #####
def _providers() -> list[tuple[str, type]]:
    layout = (("providers/drivers", "Driver"), ("providers/adapters", "Adapter"))
    modules = [
        (folder, surname, importlib.import_module(_dotted(path)))
        for folder, surname in layout
        for path in _modules(folder)
    ]
    return [
        (folder, cls)
        for folder, surname, module in modules
        for name, cls in vars(module).items()
        if isinstance(cls, type) and name.endswith(surname) and cls.__module__ == module.__name__
    ]


PROVIDERS: Final = _providers()
PORTS: Final = frozenset(path.stem for path in _modules("ports")) - {"provider"}


async def test_taxonomy_every_provider_module_holds_one() -> None:
    held = {cls.__module__ for _, cls in PROVIDERS}
    assert held == {
        _dotted(path) for folder in ("providers/drivers", "providers/adapters") for path in _modules(folder)
    }


@pytest.mark.parametrize(("folder", "cls"), PROVIDERS, ids=[cls.__name__ for _, cls in PROVIDERS])
async def test_taxonomy_provider_spec_lifecycle_locality(folder: str, cls: type) -> None:
    spec = getattr(cls, "spec", None)
    assert isinstance(spec, ProviderSpec), f"{cls.__name__} declares no ProviderSpec"
    assert all(callable(getattr(cls, name, None)) for name in LIFECYCLE), f"{cls.__name__} lacks part of the lifecycle"
    assert (spec.locality is Locality.EMBEDDED) is (folder == "providers/adapters")


@pytest.mark.parametrize(("folder", "cls"), PROVIDERS, ids=[cls.__name__ for _, cls in PROVIDERS])
async def test_taxonomy_provider_meets_its_folder_port(folder: str, cls: type) -> None:
    capability = cls.__module__.split(".")[-2]
    assert capability in PORTS, f"{cls.__name__}: {capability!r} is no module of ports/"
    module = importlib.import_module(f"etrack.ports.{capability}")
    (port,) = (
        member
        for member in vars(module).values()
        if isinstance(member, type) and member.__module__ == module.__name__ and Provider in member.__mro__
    )
    missing = sorted(member for member in get_protocol_members(port) if not hasattr(cls, member))
    assert not missing, f"{cls.__name__} does not meet {port.__name__}: lacks {missing}"


async def test_taxonomy_provider_names_unique() -> None:
    assert not [name for name, count in Counter(cls.__name__ for _, cls in PROVIDERS).items() if count > 1]


@pytest.mark.parametrize(("folder", "cls"), PROVIDERS, ids=[cls.__name__ for _, cls in PROVIDERS])
async def test_taxonomy_provider_carries_its_nature(folder: str, cls: type) -> None:
    assert cls.__name__.endswith(folder.removeprefix("providers/").title().removesuffix("s"))


##### CONFIG MIRRORS THE TREE #####
CONFIG: Final = PACKAGE / "infra" / "config"
CONFIGS: Final = sorted((CONFIG / "providers").rglob("*.py"))


@pytest.mark.parametrize("path", CONFIGS, ids=[str(path.relative_to(CONFIG)) for path in CONFIGS])
async def test_taxonomy_config_configures_a_module(path: Path) -> None:
    configured = PACKAGE / path.relative_to(CONFIG)
    assert configured.exists(), f"{path.relative_to(CONFIG)} configures no module"
    module = importlib.import_module(_dotted(path))
    scopes = [
        cls
        for cls in vars(module).values()
        if isinstance(cls, type) and issubclass(cls, BaseSettings) and cls is not BaseSettings
    ]
    assert len(scopes) == 1
