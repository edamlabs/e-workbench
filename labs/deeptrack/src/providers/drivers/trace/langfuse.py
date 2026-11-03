"""providers/drivers/trace/langfuse: LangfuseTraceDriver — Langfuse v4 over OTLP, the lab's historical record.

The SDK batches spans on an exporter thread and ships them to the server outside the process: a driver. Personal data
is masked by the same op the projector uses before any span leaves; every trace is tagged with the lab environment."""

import asyncio
from typing import ClassVar, Self

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from infra.config.providers.drivers.trace.langfuse import LangfuseSettings
from infra.errors import TelemetryError
from infra.logger import logger
from infra.settings import settings as st
from ops.mask import mask_data
from ports.provider import Isolation, Locality, ProviderSpec, Workload


class LangfuseTraceDriver:
    """One Langfuse client for the process; one callback handler per run, pinned to its derived trace."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("langfuse", Locality.SIDECAR, Workload.IO_BOUND, Isolation.THREAD)

    __slots__ = ("_client", "_settings")

    def __init__(self, settings: LangfuseSettings | None = None) -> None:
        self._settings = settings
        self._client: Langfuse | None = None

    @property
    def _common_client(self) -> Langfuse:
        match self._client:
            case None:
                msg = "langfuse: the driver is not open"
                raise TelemetryError(msg)
            case client:
                return client

    @property
    def _common_config(self) -> LangfuseSettings:
        return self._settings or st.providers.drivers.trace.langfuse

    ############################################################

    async def __aenter__(self) -> Self:
        config = self._common_config
        self._client = Langfuse(
            public_key=config.public_key,
            secret_key=config.secret_key.get_secret_value(),
            base_url=config.url,
            environment=config.environment,
            flush_interval=config.flush_interval,
            mask=mask_data,
        )
        logger.info("trace open", driver="langfuse", url=config.url, environment=config.environment)
        return self

    async def __aexit__(self, *exc: object) -> None:
        ### shutdown flushes and joins the exporter thread: blocking, so off the loop.
        await asyncio.to_thread(self._common_client.shutdown)
        self._client = None
        logger.info("trace closed", driver="langfuse")

    async def health(self) -> bool:
        """Whether the keys authenticate against the server; never raises."""
        try:
            return await asyncio.to_thread(self._common_client.auth_check)
        except Exception:  # noqa: BLE001 — health answers, it does not raise: any failure is "unhealthy"
            return False

    @staticmethod
    def trace_id(run_id: str) -> str:
        """The trace a run lands in, derived from its id."""
        return Langfuse.create_trace_id(seed=run_id)

    def handler(self, run_id: str) -> CallbackHandler:
        """The run's callback handler: every span it exports hangs from the run's trace."""
        return CallbackHandler(
            public_key=self._common_config.public_key, trace_context={"trace_id": self.trace_id(run_id)}
        )

    def url(self, trace_id: str) -> str:
        """Where the trace opens in the UI."""
        config = self._common_config
        return f"{config.url}/project/{config.project}/traces/{trace_id}"

    @staticmethod
    def session(thread: str) -> dict[str, str]:
        """The run metadata Langfuse groups a conversation by."""
        return {"langfuse_session_id": thread}

    async def flush(self) -> None:
        """Export every buffered span now."""
        await asyncio.to_thread(self._common_client.flush)
