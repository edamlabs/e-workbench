"""infra.settings: every scope's settings, read from the environment on first use — `st.<scope>.<field>`."""

from functools import cached_property

from deeptrack.infra.config.model import ModelConfig
from deeptrack.infra.config.onto import OntoConfig
from deeptrack.infra.config.trace import TraceConfig


class Settings:
    """The scopes, each validated once, lazily: a command that never touches a scope never reads its variables."""

    @cached_property
    def model(self) -> ModelConfig:
        return ModelConfig()

    @cached_property
    def onto(self) -> OntoConfig:
        return OntoConfig()

    @cached_property
    def trace(self) -> TraceConfig:
        return TraceConfig()


settings = Settings()
