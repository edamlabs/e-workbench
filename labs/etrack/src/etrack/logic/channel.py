"""logic/channel: EventChannel — the log that carries the events: reserved keys in, validated record out, fanned out.

The channel is a structlog logger of its own (`wrap_logger`), so it never touches the host's configuration and the
host's level never drops an event. Its chain: the bound context (`run_id`, `thread_id`) merged in → the keys
validated into the channel's model (`RunEvent` or a project's subclass) → the record published on the bus → a
narrowed line (`LogView` by default) forwarded to the host's own `etrack` logger at the phase's level, where the
host's rendering and filtering decide what is printed. Any code may emit: `channel.log.info("run.event", kind=…)`
with the reserved keys, or `channel.emit(event)` with a record already built — the same chain either way."""

import logging
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

import msgspec
import structlog

from etrack.infra.errors import ChannelError
from etrack.infra.logger import NAME
from etrack.models.event import EventPhase, EventView, LogView, RunEvent

if TYPE_CHECKING:
    from collections.abc import Mapping

    from structlog.typing import EventDict, WrappedLogger

    from etrack.ports.bus import BusPort

EVENT: Final[str] = "run.event"
### structlog's own keys, never fields of the record.
RESERVED: Final[frozenset[str]] = frozenset({"event", "_record"})
EMPTY: Final[tuple[object, ...]] = (None, "")
LEVELS: Final[Mapping[EventPhase, int]] = MappingProxyType(
    {
        EventPhase.START: logging.INFO,
        EventPhase.DELTA: logging.DEBUG,
        EventPhase.END: logging.INFO,
        EventPhase.ERROR: logging.ERROR,
        EventPhase.INSTANT: logging.INFO,
    }
)


class EventChannel:
    """One emission point per process: validate, publish, forward — then the line is dropped, nothing is rendered here."""

    __slots__ = ("_bus", "_forward", "_host", "_log", "_model")

    def __init__(
        self,
        bus: BusPort,
        model: type[RunEvent] = RunEvent,
        forward: type[EventView] | None = LogView,
    ) -> None:
        self._bus = bus
        self._model = model
        self._forward = forward
        self._host: Any = structlog.get_logger(NAME)
        self._log: Any = structlog.wrap_logger(
            structlog.ReturnLogger(),
            processors=[
                structlog.contextvars.merge_contextvars,
                self._emit_validate,
                self._emit_publish,
                self._emit_forward,
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging.NOTSET),
        )

    ##### PRIVATE #####

    def _emit_validate(self, _logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
        fields = {key: value for key, value in event_dict.items() if key not in RESERVED}
        try:
            record = event_dict.get("_record") or msgspec.convert(fields, self._model)
        except msgspec.ValidationError as failure:
            msg = f"{event_dict.get('event', '')}: not a {self._model.__name__} — {failure}"
            raise ChannelError(msg) from failure
        return {"event": event_dict.get("event", EVENT), "_record": record}

    def _emit_publish(self, _logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
        self._bus.publish(event_dict["_record"])
        return event_dict

    def _emit_forward(self, _logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
        record: RunEvent = event_dict["_record"]
        match self._forward:
            case None:
                pass
            case view:
                ### empty fields stay off the line: a host's log is read by people and grepped by machines.
                line = {
                    key: value
                    for key, value in msgspec.structs.asdict(view.project(record)).items()
                    if value not in EMPTY
                }
                self._host.log(LEVELS[record.phase], event_dict["event"], **line)
        raise structlog.DropEvent

    ############################################################

    ##### PUBLIC #####

    @property
    def log(self) -> Any:
        """The channel as a logger: `log.info("run.event", **reserved_keys)` validates, publishes and forwards."""
        return self._log

    @property
    def model(self) -> type[RunEvent]:
        """The record every emission is validated into."""
        return self._model

    def emit(self, event: RunEvent) -> None:
        """A record already built, through the same chain: published as is, forwarded narrowed."""
        self._log.info(EVENT, _record=event)
