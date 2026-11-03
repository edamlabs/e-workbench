"""ops.mask: personal data masked before any frame or span leaves the process — the live stream and Langfuse alike."""

import re
from collections.abc import Mapping
from typing import Any, Final

### an Argentine CUIT/CUIL, bare or hyphenated: 2 + 8 + 1 digits.
CUIT_RE: Final = re.compile(r"\b\d{2}-?\d{8}-?\d\b")
MASK: Final[str] = "[CUIT]"
LIMIT: Final[int] = 2000


def mask_text(text: str) -> str:
    """The text with every CUIT replaced."""
    return CUIT_RE.sub(MASK, text)


def mask_data(*, data: Any, **_: Any) -> Any:
    """Any JSON-like value masked in depth; Langfuse's `mask=` hook and the projector share it."""
    match data:
        case str():
            return mask_text(data)
        case Mapping():
            return {key: mask_data(data=value) for key, value in data.items()}
        case list() | tuple():
            return [mask_data(data=value) for value in data]
        case _:
            return data


def mask_clip(value: object) -> str:
    """Any value as masked text, clipped: what a frame carries of an input or an output."""
    return mask_text(str(value))[:LIMIT]
