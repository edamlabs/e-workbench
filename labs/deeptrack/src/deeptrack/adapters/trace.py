"""adapters.trace: TraceAdapter — Langfuse, the historical record of every run.

The trace id is derived from the run id (`create_trace_id(seed=…)`), so the live frames and the stored trace
name the same run without either asking the other. Personal data is masked by the same function the projector
uses before the SDK exports a span."""

import asyncio
from types import TracebackType
from typing import Self

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from deeptrack.infra.config.trace import TraceConfig
from deeptrack.ops.mask import mask_data


class TraceAdapter:
    """One Langfuse client for the process; one callback handler per run, pinned to its trace."""

    __slots__ = ("_client", "_config")

    def __init__(self, config: TraceConfig) -> None:
        self._config = config
        self._client = Langfuse(
            public_key=config.public_key,
            secret_key=config.secret_key.get_secret_value(),
            base_url=config.base_url,
            flush_interval=config.flush_interval,
            tracing_enabled=config.enabled,
            mask=mask_data,
        )

    ############################################################

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self, kind: type[BaseException] | None, error: BaseException | None, trace: TracebackType | None
    ) -> None:
        ### the SDK's shutdown flushes and joins its exporter thread: blocking, so off the loop.
        await asyncio.to_thread(self._client.shutdown)

    async def flush(self) -> None:
        """Export every span still buffered, now — off the loop, the SDK blocks."""
        await asyncio.to_thread(self._client.flush)

    @staticmethod
    def trace_id(run_id: str) -> str:
        """The Langfuse trace id a run lands in, derived — never looked up."""
        return Langfuse.create_trace_id(seed=run_id)

    def handler(self, run_id: str) -> CallbackHandler:
        """The run's callback handler: every span it exports hangs from the run's trace."""
        return CallbackHandler(public_key=self._config.public_key, trace_context={"trace_id": self.trace_id(run_id)})

    def url(self, trace_id: str) -> str:
        """Where the trace opens in the UI."""
        return f"{self._config.base_url}/project/{self._config.project}/traces/{trace_id}"
