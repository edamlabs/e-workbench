"""infra/config/providers: the providers' edges — a block per driver and adapter, named as the variables they read.

The chat model is one choice (`DEEPTRACK_CHAT_PROVIDER`): the Gemini API with the repository's key, or Gemini on
Vertex AI with Application Default Credentials. The guard's classifier shares the key. The two Open Ontologies servers
are the compose's; the agents directory is data outside the code. etrack's sinks and the lab's Langfuse close it."""

import base64
from enum import StrEnum, auto
from pathlib import Path
from typing import Annotated, Final

from pydantic import Field, PositiveFloat, SecretStr

from infra.config.base import LAB, BaseSettings

Port = Annotated[int, Field(ge=0, le=65535)]
AGENTS: Final[Path] = LAB / "agents"


##### ENUMS #####
class ChatProvider(StrEnum):
    """Gemini over its API key (the lab's default), or Gemini on Vertex AI with ADC."""

    GEMINI = auto()
    VERTEX = auto()


class ThinkingLevel(StrEnum):
    """Gemini 3+ thinking budget; the model's default is high, slow per turn."""

    MINIMAL = auto()
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()


class SinkKind(StrEnum):
    """The sinks this lab can subscribe: the live replay buffer, the terminal tree, OTLP to the lab's Langfuse."""

    LIVE = auto()
    CONSOLE = auto()
    OTLP = auto()


##### SETTINGS #####
class ProviderSettings(BaseSettings):
    """One block per driver and adapter."""

    ##### DRIVERS #####

    ### CHAT
    DEEPTRACK_CHAT_PROVIDER: ChatProvider = ChatProvider.GEMINI

    ### GEMINI
    GEMINI_API_KEY: SecretStr = SecretStr("")
    DEEPTRACK_GEMINI_REF: str = "google_genai:gemini-2.5-flash"
    DEEPTRACK_GEMINI_THINKING_LEVEL: ThinkingLevel | None = None
    DEEPTRACK_GEMINI_TIMEOUT: PositiveFloat = 120.0

    ### VERTEX
    DEEPTRACK_VERTEX_PROJECT: str | None = None
    DEEPTRACK_VERTEX_LOCATION: str = "global"
    DEEPTRACK_VERTEX_REF: str = "google_genai:gemini-3.8-flash"
    DEEPTRACK_VERTEX_THINKING_LEVEL: ThinkingLevel = ThinkingLevel.MEDIUM
    DEEPTRACK_VERTEX_TIMEOUT: PositiveFloat = 120.0

    ### GEMINI CLASSIFY
    ### measured 2026-11-03: 28/28 on the guard's probe set, p50 661 ms, max 888 ms.
    DEEPTRACK_CLASSIFY_REF: str = "google_genai:gemini-3.5-flash-lite"
    DEEPTRACK_CLASSIFY_THINKING_LEVEL: ThinkingLevel | None = ThinkingLevel.MINIMAL
    DEEPTRACK_CLASSIFY_TIMEOUT: PositiveFloat = 10.0

    ### FILES HARNESS
    DEEPTRACK_AGENTS_DIRECTORY: Path = AGENTS

    ### OPEN ONTOLOGIES
    LABS_ONTO_HOST: str = "localhost"
    LABS_ONTOREF_PORT: Port = 28101
    LABS_ONTOVAL_PORT: Port = 28102
    LABS_ONTO_TOKEN: SecretStr | None = None

    ##### ADAPTERS #####

    ### TRACK
    DEEPTRACK_TRACK_SINKS: frozenset[SinkKind] = frozenset({SinkKind.LIVE, SinkKind.OTLP})
    DEEPTRACK_TRACK_FORWARD: bool = True

    ### LANGFUSE — etrack's OTLP sink aims here; the keys are the ones `make env` generated
    LABS_LANGFUSE_HOST: str = "localhost"
    LABS_LANGFUSE_PORT: Port = 28100
    LABS_LANGFUSE_PUBLIC_KEY: str = ""
    LABS_LANGFUSE_SECRET_KEY: SecretStr = SecretStr("")
    LABS_LANGFUSE_PROJECT: str = "labs-deeptrack"
    LABS_LANGFUSE_ENVIRONMENT: str = "labs"

    @property
    def onto_ref_url(self) -> str:
        """The reference server's MCP endpoint: what the agent reads."""
        return f"http://{self.LABS_ONTO_HOST}:{self.LABS_ONTOREF_PORT}/mcp"

    @property
    def onto_val_url(self) -> str:
        """The validation server's MCP endpoint: where the gate judges."""
        return f"http://{self.LABS_ONTO_HOST}:{self.LABS_ONTOVAL_PORT}/mcp"

    @property
    def langfuse_url(self) -> str:
        """Langfuse's web, API and OTLP endpoint on the host."""
        return f"http://{self.LABS_LANGFUSE_HOST}:{self.LABS_LANGFUSE_PORT}"

    @property
    def langfuse_otlp(self) -> str:
        """The OTLP/HTTP base etrack's sink exports to (`/v1/traces` appended by the sink)."""
        return f"{self.langfuse_url}/api/public/otel"

    @property
    def langfuse_authorization(self) -> SecretStr:
        """The Basic header the keys make, secret like the key it carries."""
        pair = f"{self.LABS_LANGFUSE_PUBLIC_KEY}:{self.LABS_LANGFUSE_SECRET_KEY.get_secret_value()}"
        return SecretStr(f"Basic {base64.b64encode(pair.encode()).decode()}")

    @property
    def langfuse_traces(self) -> str:
        """Where a run's trace opens: append the run id."""
        return f"{self.langfuse_url}/project/{self.LABS_LANGFUSE_PROJECT}/traces"
