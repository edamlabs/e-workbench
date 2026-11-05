"""Fixtures of the harness driver: a writable copy of the valid roster and the open call."""

import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from providers.drivers.harness.files import FilesDriver

type Opened = Callable[[Path], Awaitable[FilesDriver]]


@pytest.fixture
def tree(tmp_path: Path, valid: Path) -> Path:
    """A writable copy of the valid roster, for a test to break."""
    return Path(shutil.copytree(valid, tmp_path / "agents"))


@pytest.fixture
def opened() -> Opened:
    """`await opened(directory)`: a driver entered over a directory."""

    async def entered(directory: Path) -> FilesDriver:
        return await FilesDriver(directory=directory).__aenter__()

    return entered
