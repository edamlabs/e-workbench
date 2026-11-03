"""ports/trace: the historical record of agent runs — one callback handler per run, pinned to a trace it can name.

A run's trace id is derived from the run id, never looked up, so a live frame and the stored trace name the same
run without either asking the other."""

from typing import Protocol, runtime_checkable

from langchain_core.callbacks import BaseCallbackHandler

from ports.provider import Provider


@runtime_checkable
class TracePort(Provider, Protocol):
    """Trace ids, per-run handlers, where a trace opens, the run metadata that groups a conversation, and a flush."""

    def trace_id(self, run_id: str) -> str: ...

    def handler(self, run_id: str) -> BaseCallbackHandler: ...

    def url(self, trace_id: str) -> str: ...

    def session(self, thread: str) -> dict[str, str]: ...

    async def flush(self) -> None: ...
