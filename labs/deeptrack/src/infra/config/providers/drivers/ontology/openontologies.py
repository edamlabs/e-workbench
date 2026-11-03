"""infra/config/providers/drivers/ontology/openontologies: the two Open Ontologies servers the lab's compose publishes."""

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from infra.config.base import BaseSettings, Secret


class OpenontologiesSettings(BaseSettings):
    """`ref` serves the agent, `val` the gate; one driver class, two instances, one port each."""

    model_config = SettingsConfigDict(env_prefix="LABS_ONTO_")

    host: str = "localhost"
    ref_port: int = Field(default=28101, validation_alias="LABS_ONTOREF_PORT")
    val_port: int = Field(default=28102, validation_alias="LABS_ONTOVAL_PORT")
    token: Secret | None = None

    @property
    def ref_url(self) -> str:
        """The reference server's MCP endpoint."""
        return f"http://{self.host}:{self.ref_port}/mcp"

    @property
    def val_url(self) -> str:
        """The validation server's MCP endpoint."""
        return f"http://{self.host}:{self.val_port}/mcp"
