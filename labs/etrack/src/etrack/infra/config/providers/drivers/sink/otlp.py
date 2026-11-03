"""infra/config/providers/drivers/sink/otlp: where spans and logs go over OTLP/HTTP, how fast, under which service."""

from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import SettingsConfigDict

from etrack.infra.config.base import BaseSettings, Secret


class OtlpTarget(BaseModel):
    """One collector: its OTLP/HTTP base URL (signals under `/v1/traces`, `/v1/logs`) and the headers it authenticates."""

    model_config = ConfigDict(frozen=True)

    endpoint: str
    headers: dict[str, Secret] = Field(default_factory=dict)


class OtlpSettings(BaseSettings):
    """ETRACK_OTLP_TARGETS — collectors by name as JSON (`{"langfuse": {"endpoint": …, "headers": {…}}}`; none: spans
    are minted, never exported); ETRACK_OTLP_TRACES / ETRACK_OTLP_LOGS — which signals leave; ETRACK_OTLP_TIMEOUT —
    per-export deadline; ETRACK_OTLP_FLUSH — how often a batch leaves; ETRACK_OTLP_SERVICE — `service.name`;
    ETRACK_OTLP_ATTRIBUTES — extra resource attributes as JSON."""

    model_config = SettingsConfigDict(env_prefix="ETRACK_OTLP_")

    targets: dict[str, OtlpTarget] = Field(default_factory=dict)
    traces: bool = True
    logs: bool = False
    timeout: timedelta = timedelta(seconds=10)
    flush: timedelta = timedelta(seconds=1)
    service: str = "etrack"
    attributes: dict[str, str] = Field(default_factory=dict)
