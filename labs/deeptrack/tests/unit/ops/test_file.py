"""tests/unit/ops/file: a markdown text split at its YAML frontmatter, or no split at all."""

import pytest

from ops.file import file_frontmatter


@pytest.mark.parametrize(
    ("text", "split"),
    [
        ("---\nname: a\n---\nbody\n", ("name: a", "body")),
        ("---\nname: a\n---\n\nbody\n\n", ("name: a", "body")),
        ("---\nname: a\n---\n", ("name: a", "")),
        ("no fence\n", None),
        ("---\nname: a\nnever closed\n", None),
        ("---", None),
    ],
    ids=["plain", "padded", "empty-body", "no-fence", "unclosed", "bare"],
)
async def test_file_frontmatter(text: str, split: tuple[str, str] | None) -> None:
    assert file_frontmatter(text) == split
