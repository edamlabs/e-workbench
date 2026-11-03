"""logic/api: Tracker — the public surface: one run tracked from a host's config, its frames on the channel.

`track(thread, config)` opens a run: a fresh `RunScope` (uuid7, the trace id too), a fold whose frames go to the
channel, the source's hook bound into the host's config, and `run_id`/`thread_id` bound in structlog's contextvars
for every log line of the block. The host runs its framework with the config it gets back; the `Tracked` it holds also
reaches the fold for spans and facts of its own code (`tracked.fold.span(…)`, `tracked.fold.instant(…)`)."""

import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from etrack.models.event import RunScope
from etrack.processors.fold import FoldProcessor, Redact

if TYPE_CHECKING:
    from collections.abc import Generator

    from etrack.logic.channel import EventChannel
    from etrack.ports.source import SourcePort


@dataclass(frozen=True, slots=True)
class Tracked[C]:
    """A run in progress: its scope, the host's config with the source bound, and the fold behind it."""

    scope: RunScope
    config: C
    fold: FoldProcessor


class Tracker[C]:
    """Runs of one framework, tracked onto one channel; `redact` is the project's mask over every payload."""

    __slots__ = ("_channel", "_redact", "_source")

    def __init__(self, channel: EventChannel, source: SourcePort[C], redact: Redact | None = None) -> None:
        self._channel = channel
        self._source = source
        self._redact = redact

    @contextmanager
    def track(self, thread: str, config: C, run_id: str | None = None) -> Generator[Tracked[C]]:
        """One run on `thread`: the scope, the bound config and the fold, with the run's ids bound for the block."""
        scope = RunScope(run_id=run_id or uuid.uuid7().hex, thread_id=thread)
        fold = FoldProcessor(scope, self._channel.emit, self._redact)
        with structlog.contextvars.bound_contextvars(run_id=scope.run_id, thread_id=scope.thread_id):
            yield Tracked(scope=scope, config=self._source.bind(fold, scope, config), fold=fold)
