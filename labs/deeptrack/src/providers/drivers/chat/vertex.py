"""providers/drivers/chat/vertex: VertexChatDriver — Gemini on Vertex AI, built and authenticated when it opens.

The work happens in Google's service: a driver. Credentials are ADC; a process without them fails at startup with a
`ModelError`, never mid-turn."""

from typing import ClassVar, Self

from google.auth.exceptions import DefaultCredentialsError
from langchain_core.language_models import BaseChatModel

from infra.config.providers.drivers.chat.vertex import VertexSettings
from infra.errors import ModelError
from infra.logger import logger
from infra.settings import settings as st
from ports.provider import Isolation, Locality, ProviderSpec, Workload
from providers.drivers.chat.google import ChatGoogle


class VertexChatDriver:
    """The chat model behind `ChatPort`, streaming, on Vertex AI."""

    spec: ClassVar[ProviderSpec] = ProviderSpec(
        "vertex", Locality.REMOTE, Workload.IO_BOUND, Isolation.LOOP, pooled=True
    )

    __slots__ = ("_model", "_settings")

    def __init__(self, settings: VertexSettings | None = None) -> None:
        self._settings = settings
        self._model: ChatGoogle | None = None

    ############################################################

    async def __aenter__(self) -> Self:
        config: VertexSettings = self._settings or st.providers.drivers.chat.vertex
        try:
            self._model = ChatGoogle(model=config.ref.removeprefix("google_genai:"), **config.kwargs)
        except DefaultCredentialsError as error:
            msg = f"vertex: no application default credentials ({error})"
            raise ModelError(msg) from error
        logger.info("chat open", driver="vertex", model=config.ref, project=config.project, location=config.location)
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
