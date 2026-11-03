"""infra.config.trace: the Langfuse project runs land in — the house stack's headless defaults (stack/watch/langfuse)."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class TraceConfig(BaseSettings):
    """Keys, endpoint and batching; `flush_interval` is the SDK's export delay, the knob the audit measures."""

    model_config = SettingsConfigDict(env_prefix="LANGFUSE_", frozen=True)

    public_key: str = "pk-lf-local"
    secret_key: SecretStr = SecretStr("sk-lf-local")
    base_url: str = "http://localhost:3000"
    project: str = "local"
    flush_interval: float = 5.0
    enabled: bool = True
