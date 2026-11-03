"""infra/config/providers/drivers/chat/gemini: Gemini over the Gemini API — one key, read from the repo's `.env`.

The key lives in the repository root's `.env` (shared by every lab) and may be overridden by the lab's own. Both
files outrank the process environment here, on purpose: a shell can carry a stale `GEMINI_API_KEY`, and a lab that
silently picks it up fails on a key nobody chose."""

from pathlib import Path
from typing import Any, Final

from pydantic import Field
from pydantic_settings import BaseSettings as SettingsBase
from pydantic_settings import PydanticBaseSettingsSource, SettingsConfigDict

from infra.config.base import BaseSettings, Secret
from infra.config.providers.drivers.chat.vertex import ThinkingLevel

LAB: Final[Path] = Path(__file__).resolve().parents[6]
FILES: Final[tuple[Path, ...]] = (LAB.parents[1] / ".env", LAB / ".env")


class GeminiSettings(BaseSettings):
    """`ref` is an `init_chat_model` reference; `api_key` is `GEMINI_API_KEY` from the `.env` files."""

    model_config = SettingsConfigDict(env_prefix="DEEPTRACK_GEMINI_", env_file=FILES)

    api_key: Secret = Field(default=Secret(""), validation_alias="GEMINI_API_KEY")
    ref: str = "google_genai:gemini-2.5-flash"
    thinking_level: ThinkingLevel | None = None
    timeout: float = 120.0

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[SettingsBase],  # noqa: ARG003 — pydantic-settings fixes this signature
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        ### the `.env` files beat the shell: see the module docstring.
        return (init_settings, dotenv_settings, env_settings, file_secret_settings)

    @property
    def kwargs(self) -> dict[str, Any]:
        """What `init_chat_model` hands `ChatGoogleGenerativeAI`: the API backend, never Vertex; streaming on.

        `output_version="v1"`: with tools bound, the legacy shape streams a signed text block followed by bare strings,
        and AG-UI's adapter reads only the first block — the reply arrives cut. v1 keeps one text block per message."""
        level = {"thinking_level": str(self.thinking_level)} if self.thinking_level else {}
        return {
            "vertexai": False,
            "api_key": self.api_key.get_secret_value(),
            "timeout": self.timeout,
            "streaming": True,
            "output_version": "v1",
            **level,
        }
