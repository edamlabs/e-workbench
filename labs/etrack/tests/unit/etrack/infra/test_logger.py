"""tests/unit/etrack/infra/logger: the library's lazy named logger writes through the host's configuration."""

from structlog.testing import capture_logs

from etrack.infra.logger import logger


async def test_logger_host_configured() -> None:
    with capture_logs() as lines:
        logger.info("bus opened", sinks=["live"])
    assert lines == [{"event": "bus opened", "sinks": ["live"], "log_level": "info"}]
