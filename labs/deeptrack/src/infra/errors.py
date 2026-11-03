"""infra/errors: the one root of every error — each layer imports its exceptions from here, none defines its own.

`CoreError` is the root. Four branches hang from it, one per kind of module: `ProviderError` (a provider failed at its
border), `EngineError`, `ProcessorError` and `OpsError`. Providers translate the exceptions of their library into the
provider branch; no upper layer imports a library's own. Trimmed from e-arkhetypo common to what this lab raises."""


##### ROOT #####
class CoreError(Exception):
    """All lab exceptions inherit from this root."""

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


class TelemetryError(DriverError):
    """A tracer that is not open, or whose collector cannot be reached."""


class ModelError(DriverError):
    """A model server that answered nothing usable, or one the process cannot authenticate against."""


class OntologyError(DriverError):
    """An ontology server that cannot be reached, lacks a tool, or answers a tool call with an error."""


##### ENGINES #####
class EngineError(CoreError):
    """An engine refused a request before touching any resource."""


class ShaclError(EngineError):
    """A validation round whose report is not the SHACL report the engine reads."""


##### PROCESSORS #####
class ProcessorError(CoreError):
    """A processor refused its input."""


##### OPS #####
class OpsError(CoreError):
    """An agnostic tool refused its input."""


class FileError(OpsError, TypeError):
    """A discover target the file tool refuses to interpret."""
