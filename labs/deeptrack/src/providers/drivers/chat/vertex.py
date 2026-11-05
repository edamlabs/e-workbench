"""providers/drivers/chat/vertex: VertexDriver — Gemini on Vertex AI, built and authenticated when it opens.

The work happens in Google's service: a driver. Credentials are ADC; a process without them fails at startup with a
`ModelError`, never mid-turn."""

from typing import Any, ClassVar, Self

from google.auth.exceptions import DefaultCredentialsError
from langchain_core.language_models import BaseChatModel

from infra.config.providers import ThinkingLevel
from infra.errors import ModelError
from infra.logger import logger
from ports.provider import Isolation, Locality, ProviderSpec, Workload
from providers.drivers.chat.google import ChatGoogle


class VertexDriver:
    """The chat model behind `ChatPort`, streaming, on Vertex AI."""

    spec: ClassVar[ProviderSpec] = ProviderSpec(
        "vertex", Locality.REMOTE, Workload.IO_BOUND, Isolation.LOOP, pooled=True
    )

    __slots__ = ("_location", "_model", "_project", "_ref", "_thinking", "_timeout")

    def __init__(
        self,
        *,
        ref: str,
        project: str | None = None,
        location: str = "global",
        thinking: ThinkingLevel = ThinkingLevel.MEDIUM,
        timeout: float = 120.0,
    ) -> None:
        self._ref = ref
        self._project = project
        self._location = location
        self._thinking = thinking
        self._timeout = timeout
        self._model: ChatGoogle | None = None

    ############################################################

    async def __aenter__(self) -> Self:
        try:
            ### streaming makes tokens reach the callbacks; v1 keeps one text block per message.
            options: dict[str, Any] = {
                "vertexai": True,
                "project": self._project,
                "location": self._location,
                "thinking_level": str(self._thinking),
                "timeout": self._timeout,
                "streaming": True,
                "output_version": "v1",
            }
            self._model = ChatGoogle(model=self._ref.removeprefix("google_genai:"), **options)
        except DefaultCredentialsError as error:
            msg = f"vertex: no application default credentials ({error})"
            raise ModelError(msg) from error
        logger.info("chat open", driver="vertex", model=self._ref, project=self._project, location=self._location)
        return self

    async def __aexit__(self, *exc: object) -> None:
        match self._model:
            case ChatGoogle() as model:
                await model.aclose()
            case None:
                pass
        self._model = None
        logger.info("chat closed", driver="vertex")

    async def health(self) -> bool:
        return self._model is not None

    @property
    def model(self) -> BaseChatModel:
        """The chat model; reading it on a closed driver is a wiring bug."""
        match self._model:
            case None:
                msg = "vertex: the driver is not open"
                raise ModelError(msg)
            case model:
                return model
