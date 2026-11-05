"""providers/drivers/chat/gemini: ChatGeminiDriver — Gemini over the Gemini API with an API key.

The work happens in Google's service: a driver. A missing key fails at startup with a `ModelError`, never mid-turn;
the key is passed explicitly, so a stale `GOOGLE_API_KEY` in the environment never wins."""

from typing import Any, ClassVar, Self

from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

from infra.config.providers import ThinkingLevel
from infra.errors import ModelError
from infra.logger import logger
from ports.provider import Isolation, Locality, ProviderSpec, Workload
from providers.drivers.chat.google import ChatGoogle


class ChatGeminiDriver:
    """The chat model behind `ChatPort`, streaming, on the Gemini API."""

    spec: ClassVar[ProviderSpec] = ProviderSpec(
        "gemini", Locality.REMOTE, Workload.IO_BOUND, Isolation.LOOP, pooled=True
    )

    __slots__ = ("_api_key", "_model", "_ref", "_thinking", "_timeout")

    def __init__(
        self, *, ref: str, api_key: SecretStr, thinking: ThinkingLevel | None = None, timeout: float = 120.0
    ) -> None:
        self._ref = ref
        self._api_key = api_key
        self._thinking = thinking
        self._timeout = timeout
        self._model: ChatGoogle | None = None

    ############################################################

    async def __aenter__(self) -> Self:
        match self._api_key.get_secret_value():
            case "":
                msg = "gemini: no GEMINI_API_KEY in the repository's or the lab's .env"
                raise ModelError(msg)
            case key:
                ### the API backend, never Vertex; streaming on. `output_version="v1"`: with tools bound, the legacy shape
                ### streams a signed text block then bare strings, and AG-UI's adapter reads only the first — cut replies.
                level: dict[str, Any] = {"thinking_level": str(self._thinking)} if self._thinking else {}
                self._model = ChatGoogle(
                    model=self._ref.removeprefix("google_genai:"),
                    vertexai=False,
                    api_key=key,
                    timeout=self._timeout,
                    streaming=True,
                    output_version="v1",
                    **level,
                )
        logger.info("chat open", driver="gemini", model=self._ref)
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
