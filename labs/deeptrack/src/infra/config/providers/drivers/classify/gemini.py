"""infra/config/providers/drivers/classify/gemini: the guard's classifier — Gemini Flash-Lite, minimal thinking.

The same key and the same `.env` precedence as the chat model; a cheaper, faster model on an enum schema."""

from pydantic_settings import SettingsConfigDict

from infra.config.providers.drivers.chat.gemini import FILES, GeminiSettings
from infra.config.providers.drivers.chat.vertex import ThinkingLevel


class GeminiClassifySettings(GeminiSettings):
    """`ref` the classifier model; measured 2026-11-03: 28/28 on the guard's probe set, p50 661 ms, max 888 ms."""

    model_config = SettingsConfigDict(env_prefix="DEEPTRACK_CLASSIFY_", env_file=FILES)

    ref: str = "google_genai:gemini-3.5-flash-lite"
    thinking_level: ThinkingLevel | None = ThinkingLevel.MINIMAL
    timeout: float = 10.0
