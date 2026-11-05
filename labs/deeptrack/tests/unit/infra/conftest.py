"""Fixtures of the settings gates: the environment names a settings class reads, and the source tree below the root."""

import ast
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Final

import pytest
from pydantic import BaseModel

SOURCE: Final[Path] = Path(__file__).resolve().parents[3] / "src"
CONFIG: Final[Path] = SOURCE / "infra" / "config"
SNAPSHOT: Final[Path] = Path(__file__).resolve().parents[2] / "resources" / "settings" / "env.json"
### the composition root: the entrypoint, the ASGI app, the lifespans, the cli's commands.
ROOT: Final[re.Pattern[str]] = re.compile(r"^(main|api/app)\.py$|^infra/lifespan/|^cli/commands/")

type Names = Callable[[type[BaseModel]], set[str]]
type Imports = list[tuple[str, str, str]]


@pytest.fixture
def names() -> Names:
    """`names(model)`: the environment names a settings class reads — each field, and `FIELD__KEY` into a model."""

    def read(model: type[BaseModel]) -> set[str]:
        nested = (
            f"{name}__{key.upper()}"
            for name, field in model.model_fields.items()
            for kind in (field.annotation, *getattr(field.annotation, "__args__", ()))
            if isinstance(kind, type) and issubclass(kind, BaseModel)
            for key in kind.model_fields
        )
        return {*model.model_fields, *nested}

    return read


@pytest.fixture
def snapshot() -> list[str]:
    """The environment names a deployment sets, as committed: a rename is a deployment change."""
    return json.loads(SNAPSHOT.read_text())


@pytest.fixture
def below() -> Imports:
    """Every `from <module> import <name>` of the modules below the composition root, with the module's path."""
    paths = [
        path
        for path in SOURCE.rglob("*.py")
        if CONFIG not in path.parents
        and path != SOURCE / "infra" / "settings.py"
        and not ROOT.search(str(path.relative_to(SOURCE)))
    ]
    return [
        (str(path.relative_to(SOURCE)), node.module or "", alias.name)
        for path in paths
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    ]
