"""infra/config/chat: which provider meets the chat port — the one choice the providers lifespan reads."""

from enum import StrEnum, auto

from pydantic_settings import SettingsConfigDict

from infra.config.base import BaseSettings


class ChatProvider(StrEnum):
    """Gemini over its API key (the lab's default), or Gemini on Vertex AI with ADC."""

    GEMINI = auto()
    VERTEX = auto()


class ChatSettings(BaseSettings):
    """`DEEPTRACK_CHAT_PROVIDER` picks the driver; each driver keeps its own scope."""

    model_config = SettingsConfigDict(env_prefix="DEEPTRACK_CHAT_")

    provider: ChatProvider = ChatProvider.GEMINI
