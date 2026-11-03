"""infra.config.trace: the Langfuse project runs land in — the same `LABS_LANGFUSE_*` variables compose seeds it with."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class TraceConfig(BaseSettings):
    """Keys, port and batching; `flush_interval` is the SDK's export delay, the knob the audit measures."""

    model_config = SettingsConfigDict(env_prefix="LABS_LANGFUSE_", frozen=True)

    public_key: str = "pk-lf-labs"
    secret_key: SecretStr = SecretStr("sk-lf-labs")
    host: str = "localhost"
    port: int = 28100
    project: str = "deeptrack"
    flush_interval: float = 5.0
    enabled: bool = True

    @property
    def base_url(self) -> str:
        """Langfuse's web, API and OTLP endpoint on the host."""
        return f"http://{self.host}:{self.port}"
