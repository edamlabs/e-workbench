"""ops/w3c: W3C trace-context ids derived from etrack ids — the same run and span named alike in every backend.

A run id that is 32 hex (a uuid7's hex) is its trace id as is; a span id is a frame id's low 64 bits, a uuid7's random
half. Any other id is hashed into the width it needs. Neither is ever zero: W3C reserves zero for "no id"."""

import hashlib
import re
from typing import Final

HEX: Final = re.compile(r"^[0-9a-f]{32}$")


def w3c_trace(run_id: str) -> int:
    """A run's W3C trace id: the run id itself when it is 32 hex, its digest otherwise; never zero."""
    hexed = run_id if HEX.fullmatch(run_id) else hashlib.sha256(run_id.encode()).hexdigest()[:32]
    return int(hexed, 16) or 1


def w3c_span(span: str) -> int:
    """A frame's W3C span id: the low 64 bits of its id when hex, its digest otherwise; never zero."""
    hexed = span[-16:] if HEX.fullmatch(span) else hashlib.sha256(span.encode()).hexdigest()[:16]
    return int(hexed, 16) or 1
