"""Fixtures of the providers tier: the valid agents directory every harness-reading test starts from."""

from pathlib import Path

import pytest


@pytest.fixture
def valid() -> Path:
    """The resources' valid roster directory."""
    return Path(__file__).resolve().parents[2] / "resources" / "agents" / "valid"
