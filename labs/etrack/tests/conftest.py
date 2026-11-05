"""tests: session-wide — nothing leaves the process: no ETRACK_* variable of the developer's shell reaches a test."""

import os

import pytest

### the integration tier reads where its collector is; nothing else of the shell reaches a test.
KEPT = "ETRACK_TEST_"


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every ETRACK_* variable unset for the test: settings read their defaults or what the test sets."""
    _ = [monkeypatch.delenv(key) for key in list(os.environ) if key.startswith("ETRACK_") and not key.startswith(KEPT)]
