"""tests/unit/etrack/infra/settings: the composed tree mirrors the config modules; env reaches each scope by prefix."""

import pytest

from etrack.infra.config.providers.adapters.bus.anyio import AnyioSettings
from etrack.infra.config.providers.drivers.sink.otlp import OtlpSettings
from etrack.infra.settings import Settings
from etrack.infra.settings import settings as st


async def test_settings_chain_mirrors_tree() -> None:
    assert isinstance(st.providers.adapters.bus.anyio, AnyioSettings)
    assert isinstance(st.providers.drivers.sink.otlp, OtlpSettings)
    assert st.providers.adapters.sink.live.buffer == 2000


async def test_settings_env_by_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ETRACK_BUS_CAPACITY", "7")
    monkeypatch.setenv("ETRACK_OTLP_TARGETS", '{"lf": {"endpoint": "http://x", "headers": {"A": "s"}}}')
    loaded = Settings.load()
    assert loaded.providers.adapters.bus.anyio.capacity == 7
    target = loaded.providers.drivers.sink.otlp.targets["lf"]
    assert (target.endpoint, target.headers["A"].get_secret_value()) == ("http://x", "s")


async def test_settings_override_reaches_scope() -> None:
    loaded = Settings.load(providers={"adapters": {"bus": {"anyio": {"capacity": 3}}}})
    assert loaded.providers.adapters.bus.anyio.capacity == 3


async def test_settings_frozen() -> None:
    with pytest.raises(ValueError, match="frozen"):
        AnyioSettings().capacity = 2
