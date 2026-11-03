"""providers/drivers/chat/gemini: GeminiChatDriver — Gemini over the Gemini API with an API key.

The work happens in Google's service: a driver. A missing key fails at startup with a `ModelError`, never mid-turn;
the key is passed explicitly, so a stale `GOOGLE_API_KEY` in the environment never wins."""

from typing import ClassVar, Self

from langchain_core.language_models import BaseChatModel

from infra.config.providers.drivers.chat.gemini import GeminiSettings
from infra.errors import ModelError
from infra.logger import logger
from infra.settings import settings as st
from ports.provider import Isolation, Locality, ProviderSpec, Workload
from providers.drivers.chat.google import ChatGoogle


class GeminiChatDriver:
    """The chat model behind `ChatPort`, streaming, on the Gemini API."""

    spec: ClassVar[ProviderSpec] = ProviderSpec(
        "gemini", Locality.REMOTE, Workload.IO_BOUND, Isolation.LOOP, pooled=True
    )

    __slots__ = ("_model", "_settings")

    def __init__(self, settings: GeminiSettings | None = None) -> None:
        self._settings = settings
        self._model: ChatGoogle | None = None

    ############################################################

    async def __aenter__(self) -> Self:
        config: GeminiSettings = self._settings or st.providers.drivers.chat.gemini
        match config.api_key.get_secret_value():
            case "":
                msg = "gemini: no GEMINI_API_KEY in the repository's or the lab's .env"
                raise ModelError(msg)
            case _:
                self._model = ChatGoogle(model=config.ref.removeprefix("google_genai:"), **config.kwargs)
        logger.info("chat open", driver="gemini", model=config.ref)
        return self

    async def __aexit__(self, *exc: object) -> None:
        match self._model:
            case ChatGoogle() as model:
                await model.aclose()
            case None:
                pass
        self._model = None
        logger.info("chat closed", driver="gemini")

    async def health(self) -> bool:
        return self._model is not None

    @property
    def model(self) -> BaseChatModel:
        """The chat model; reading it on a closed driver is a wiring bug."""
        match self._model:
            case None:
                msg = "gemini: the driver is not open"
                raise ModelError(msg)
            case model:
                return model
