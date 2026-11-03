"""ops/mask: personal data masked before any frame or span leaves the process — the live stream and the tracer alike."""

import dataclasses
import re
from collections.abc import Mapping
from typing import Any, Final

from pydantic import BaseModel

### an Argentine CUIT/CUIL, bare or hyphenated: 2 + 8 + 1 digits.
CUIT_RE: Final = re.compile(r"\b\d{2}-?\d{8}-?\d\b")
MASK: Final[str] = "[CUIT]"
LIMIT: Final[int] = 2000


def mask_text(text: str) -> str:
    """The text with every CUIT replaced."""
    return CUIT_RE.sub(MASK, text)


def mask_data(*, data: Any, **_: Any) -> Any:  # noqa: PLR0911 — one return per case of the dispatch
    """Any value masked in depth; a tracer's mask hook and the projector share it.

    A tracer hands the hook raw objects before it serializes them — chat messages (pydantic), graph commands
    (dataclasses), anything a node returns. Structures are walked; primitives pass; any other object is masked as its
    text: left whole, the tracer would serialize it later, personal data included. Privacy wins over fidelity."""
    match data:
        case str():
            return mask_text(data)
        case bool() | int() | float() | None:
            return data
        case BaseModel():
            return mask_data(data=data.model_dump())
        case Mapping():
            return {key: mask_data(data=value) for key, value in data.items()}
        case list() | tuple() | set() | frozenset():
            return [mask_data(data=value) for value in data]
        case _ if dataclasses.is_dataclass(data) and not isinstance(data, type):
            return {each.name: mask_data(data=getattr(data, each.name)) for each in dataclasses.fields(data)}
        case _:
            return mask_text(str(data))


def mask_clip(value: object) -> str:
    """Any value as masked text, clipped: what a frame carries of an input or an output."""
    return mask_text(str(value))[:LIMIT]
