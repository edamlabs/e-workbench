"""infra.logger: structlog on stderr — stdout belongs to the live stream."""

import logging
import sys

import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    logger_factory=structlog.PrintLoggerFactory(sys.stderr),
)
logger = structlog.get_logger()
