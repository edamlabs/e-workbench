"""providers/drivers/classify/gemini: GeminiClassifyDriver — one label out of a closed set, by Gemini Flash-Lite.

The model answers under a JSON schema whose only field is an enum of the labels: it cannot say anything else. A
library failure (network, quota, a refused key) is a `ModelError` at this border."""

from typing import Any, ClassVar, Self

from langchain_core.runnables import RunnableConfig
from langchain_google_genai._common import GoogleGenerativeAIError

from infra.config.providers.drivers.classify.gemini import GeminiClassifySettings
from infra.errors import ModelError
from infra.logger import logger
from infra.settings import settings as st
from ports.provider import Isolation, Locality, ProviderSpec, Workload
from providers.drivers.chat.google import ChatGoogle


class GeminiClassifyDriver:
    """The classifier behind `ClassifyPort`."""

    spec: ClassVar[ProviderSpec] = ProviderSpec(
        "gemini-classify", Locality.REMOTE, Workload.IO_BOUND, Isolation.LOOP, pooled=True
    )

    __slots__ = ("_model", "_settings")

    def __init__(self, settings: GeminiClassifySettings | None = None) -> None:
        self._settings = settings
        self._model: ChatGoogle | None = None

    @staticmethod
    def _classify_schema(labels: tuple[str, ...]) -> dict[str, Any]:
        return {
            "title": "Verdict",
            "type": "object",
            "properties": {"label": {"type": "string", "enum": list(labels)}},
            "required": ["label"],
        }

    ############################################################

    async def __aenter__(self) -> Self:
        config: GeminiClassifySettings = self._settings or st.providers.drivers.classify.gemini
        match config.api_key.get_secret_value():
            case "":
                msg = "gemini-classify: no GEMINI_API_KEY in the repository's or the lab's .env"
                raise ModelError(msg)
            case key:
                options: dict[str, Any] = {"api_key": key, "vertexai": False, "timeout": config.timeout}
                options |= {"thinking_level": str(config.thinking_level)} if config.thinking_level else {}
                self._model = ChatGoogle(model=config.ref.removeprefix("google_genai:"), **options)
        logger.info("classify open", driver="gemini", model=config.ref)
        return self

    async def __aexit__(self, *exc: object) -> None:
        match self._model:
            case ChatGoogle() as model:
                await model.aclose()
            case None:
                pass
        self._model = None
        logger.info("classify closed", driver="gemini")

    async def health(self) -> bool:
        return self._model is not None

    async def classify(
        self, system: str, text: str, labels: tuple[str, ...], config: RunnableConfig | None = None
    ) -> str:
        """Exactly one of `labels` for `text`."""
        match self._model:
            case None:
                msg = "gemini-classify: the driver is not open"
                raise ModelError(msg)
            case model:
                structured = model.with_structured_output(self._classify_schema(labels), method="json_schema")
                try:
                    verdict = await structured.ainvoke([("system", system), ("human", text)], config)
                except GoogleGenerativeAIError as error:
                    msg = f"gemini-classify: {error}"
                    raise ModelError(msg) from error
        match verdict:
            case {"label": str() as label} if label in labels:
                return label
            case other:
                msg = f"gemini-classify: an answer outside the labels ({other!r})"
                raise ModelError(msg)
