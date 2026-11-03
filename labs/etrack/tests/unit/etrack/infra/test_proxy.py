"""tests/unit/etrack/infra/proxy: lazy singletons — nothing built at construction, exactly one build on first access."""

from etrack.infra.proxy import LazyProxy


async def test_proxy_builds_once_on_first_access() -> None:
    builds: list[int] = []
    proxy: LazyProxy[list[int]] = LazyProxy(lambda: builds.append(1) or [])
    assert builds == []
    proxy.append(7)
    proxy.append(8)
    assert builds == [1]
    assert proxy.count(8) == 1
