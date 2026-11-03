"""infra.config.onto: the two Open Ontologies servers — the ports compose publishes — and the files they hold."""

from pathlib import Path
from typing import Final

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT: Final[Path] = Path(__file__).resolve().parents[4]


class OntoConfig(BaseSettings):
    """`ref` serves the agent, `val` the gate; `files` load in order — the schema, then the data."""

    model_config = SettingsConfigDict(env_prefix="LABS_ONTO_", frozen=True)

    host: str = "localhost"
    ref_port: int = Field(default=28101, validation_alias="LABS_ONTOREF_PORT")
    val_port: int = Field(default=28102, validation_alias="LABS_ONTOVAL_PORT")
    token: SecretStr | None = None
    directory: Path = ROOT / "ontology"
    files: tuple[str, ...] = ("seguros.ttl", "datos.ttl")
    shapes: str = "formas.ttl"

    @property
    def ref_url(self) -> str:
        """The reference server's MCP endpoint."""
        return f"http://{self.host}:{self.ref_port}/mcp"

    @property
    def val_url(self) -> str:
        """The validation server's MCP endpoint."""
        return f"http://{self.host}:{self.val_port}/mcp"
