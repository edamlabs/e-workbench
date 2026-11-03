"""infra/logger: the library's own diagnostics — structlog's lazy logger, configured by the host, never by etrack.

A library never calls `structlog.configure`: the application owns rendering, level and destination. `logger` is the
named, lazy logger every etrack module writes its lifecycle and degraded paths to; its lines land wherever the host's
configuration sends them."""

from typing import Any, Final

import structlog

NAME: Final[str] = "etrack"

logger: Any = structlog.get_logger(NAME)
