"""infra/config/providers/drivers/chat/vertex: Gemini on Vertex AI, as marvin runs it — ADC, a project, a location."""

from enum import StrEnum, auto
from typing import Any

from pydantic_settings import SettingsConfigDict

from infra.config.base import BaseSettings


class ThinkingLevel(StrEnum):
    """Gemini 3+ thinking budget; the model's default is high, slow per turn."""

    MINIMAL = auto()
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()


class VertexSettings(BaseSettings):
    """`ref` is an `init_chat_model` reference; credentials are ADC (`gcloud auth application-default login`)."""

    model_config = SettingsConfigDict(env_prefix="DEEPTRACK_VERTEX_")

    project: str | None = None
    location: str = "global"
    ref: str = "google_genai:gemini-3.8-flash"
    thinking_level: ThinkingLevel = ThinkingLevel.MEDIUM
    timeout: float = 120.0

    @property
    def kwargs(self) -> dict[str, Any]:
        """What `init_chat_model` hands `ChatGoogleGenerativeAI`; streaming makes tokens reach the callbacks."""
        return {
            "vertexai": True,
            "project": self.project,
            "location": self.location,
            "thinking_level": str(self.thinking_level),
            "timeout": self.timeout,
            "streaming": True,
            "output_version": "v1",
        }
