"""tests/unit/etrack/infra/errors: one root, one branch per kind of module, sinks honestly of both natures."""

import inspect

import pytest

from etrack.infra import errors
from etrack.infra.errors import AdapterError, CoreError, DriverError, SinkError

CLASSES = [cls for _, cls in inspect.getmembers(errors, inspect.isclass) if cls.__module__ == errors.__name__]


@pytest.mark.parametrize("cls", CLASSES, ids=[cls.__name__ for cls in CLASSES])
async def test_errors_one_root(cls: type[Exception]) -> None:
    assert issubclass(cls, CoreError)
    assert cls("why").message == "why"


async def test_errors_sink_both_natures() -> None:
    assert issubclass(SinkError, DriverError)
    assert issubclass(SinkError, AdapterError)
