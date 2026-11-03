"""infra/errors: the one root of every error — each layer imports its exceptions from here, none defines its own.

`CoreError` is the root. One branch per kind of module: `ProviderError` (a provider failed at its border), `ProcessorError`,
`LogicError` and `OpsError`. A provider fails as a **driver** (`DriverError`: a system outside the process) or as an
**adapter** (`AdapterError`: a library inside it). A sink is met on both natures — the OTLP exporter over the wire,
the live buffer in memory — so `SinkError` is honestly both."""


##### ROOT #####
class CoreError(Exception):
    """All etrack exceptions inherit from this root."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


##### PROVIDERS #####
class ProviderError(CoreError):
    """A provider failed at its border: what a third-party library raised, or a call on a provider that is not open."""


class DriverError(ProviderError):
    """A system outside the process failed: unreachable, refusing, slow, or answering outside its contract."""


class AdapterError(ProviderError):
    """A library inside the process failed: it refused its input, or the provider it wraps is not open."""


class SinkError(DriverError, AdapterError):
    """A sink that is not open, or refused what it was sent."""


class BusError(AdapterError):
    """The bus is not open, or was asked to deliver through a closed stream."""


class SourceError(AdapterError):
    """A source that cannot bind a run: the host's config is not of the shape its framework takes."""


##### PROCESSORS #####
class ProcessorError(CoreError):
    """A transformation refused its input."""


class LayoutError(ProcessorError, ValueError):
    """A topology that cannot be placed: an edge to a node it does not declare."""


##### LOGIC #####
class LogicError(CoreError):
    """The library's core refused a call."""


class ChannelError(LogicError, ValueError):
    """An event the channel cannot validate against its model: a reserved key missing or of the wrong type."""


##### OPS #####
class OpsError(CoreError):
    """An agnostic tool refused its input."""


class FileError(OpsError, TypeError):
    """A discovery target of a kind the finder does not sweep."""
