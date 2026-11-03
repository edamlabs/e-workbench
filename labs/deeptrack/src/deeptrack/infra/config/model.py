"""infra.config.model: the chat model every agent speaks through — Gemini on Vertex AI, as marvin runs it."""

from enum import StrEnum, auto
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class ThinkingLevel(StrEnum):
    """Gemini 3+ thinking budget; the model's default is high, slow per turn."""

    MINIMAL = auto()
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()


class ModelConfig(BaseSettings):
    """`ref` is an `init_chat_model` reference; Vertex needs a project and ADC (`gcloud auth application-default login`)."""

    model_config = SettingsConfigDict(env_prefix="DEEPTRACK_MODEL_", frozen=True)

    ref: str = "google_genai:gemini-3.8-flash"
    vertexai: bool = True
    project: str | None = None
    location: str = "global"
    thinking_level: ThinkingLevel = ThinkingLevel.MEDIUM
    timeout: float = 120.0

    @property
    def kwargs(self) -> dict[str, Any]:
        """What `init_chat_model` passes on to `ChatGoogleGenerativeAI`; streaming makes tokens reach the callbacks."""
        return {
            "vertexai": self.vertexai,
            "project": self.project,
            "location": self.location,
            "thinking_level": str(self.thinking_level),
            "timeout": self.timeout,
            "streaming": True,
        }
