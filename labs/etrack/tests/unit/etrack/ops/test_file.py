"""tests/unit/etrack/ops/file: FileFinder — agnostic discovery over a package (the settings composer's engine)."""

import re
from typing import TYPE_CHECKING, Any, cast

import pytest

from etrack.infra import proxy
from etrack.infra.config.base import BaseSettings
from etrack.infra.errors import FileError
from etrack.ops.file import FileFinder, Kind

if TYPE_CHECKING:
    from pathlib import Path

INFRA = FileFinder("etrack.infra")
CONFIG = FileFinder("etrack.infra.config", recursive=True)


async def test_file_modules_skip_packages() -> None:
    assert {"errors", "logger", "proxy", "settings"} <= set(INFRA.discover(Kind.MODULES))
    assert "config" not in INFRA.discover(Kind.MODULES)


async def test_file_recursive_names_by_path() -> None:
    assert "providers.drivers.sink.otlp" in CONFIG.discover(Kind.MODULES)


async def test_file_classes_and_functions_own_only() -> None:
    assert "LazyProxy" in INFRA.discover(Kind.CLASSES)
    assert "Any" not in INFRA.discover(Kind.CLASSES)
    assert FileFinder("etrack.ops").discover(Kind.FUNCTIONS).keys() >= {"w3c_trace", "w3c_span"}


async def test_file_base_and_pattern() -> None:
    found = CONFIG.discover(BaseSettings, pattern=re.compile(r"^Otlp"))
    assert set(found) == {"OtlpSettings"}
    assert "BaseSettings" not in CONFIG.discover(BaseSettings)


async def test_file_predicate_and_module() -> None:
    assert set(INFRA.discover(proxy)) == {"LazyProxy"}
    assert "LazyProxy" in INFRA.discover(lambda obj: isinstance(obj, type) and obj.__name__.endswith("Proxy"))


async def test_file_rejects_target() -> None:
    with pytest.raises(FileError, match="Unsupported discover target"):
        INFRA.discover(cast("Any", 42))


async def test_file_private_never_seen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pkgx").mkdir()
    (tmp_path / "pkgx" / "_hidden.py").write_text('"""h."""\nclass Hidden: ...\n')
    (tmp_path / "pkgx" / "shown.py").write_text('"""s."""\nclass Shown: ...\n')
    monkeypatch.syspath_prepend(str(tmp_path))
    finder = FileFinder("pkgx")
    assert set(finder.discover(Kind.MODULES)) == {"shown"}
    assert finder.summaries() == {"shown": "s."}
    assert await finder.asummaries() == {"shown": "s."}
    assert set(await finder.adiscover(Kind.CLASSES)) == {"Shown"}
