"""tests/unit/test_descriptions: every module of etrack opens with one short sentence that starts with its path."""

import ast
from pathlib import Path
from typing import Final

import pytest

PACKAGE: Final = Path(__file__).resolve().parents[2] / "src" / "etrack"
LIMIT: Final = 120
### read at collection, never inside a test: the event loop does no file I/O.
MODULES: Final = [
    (str(path.relative_to(PACKAGE).with_suffix("")), ast.get_docstring(ast.parse(path.read_text("utf-8"))))
    for path in sorted(PACKAGE.rglob("*.py"))
    if "__pycache__" not in path.parts
]


@pytest.mark.parametrize(("relpath", "doc"), MODULES, ids=[name for name, _ in MODULES])
async def test_descriptions_module_prefixed(relpath: str, doc: str | None) -> None:
    assert doc, f"{relpath}: no docstring"
    first = doc.splitlines()[0].strip()
    assert first.startswith(f"{relpath}: "), f"{relpath}: top line must start with its path"
    assert first.endswith("."), f"{relpath}: top line must be one finished sentence"
    assert len(first) <= LIMIT, f"{relpath}: top description must stay short ({len(first)})"
