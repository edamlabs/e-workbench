"""infra.config.onto: the two Open Ontologies servers and the ontology files they hold."""

from pathlib import Path
from typing import Final

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT: Final[Path] = Path(__file__).resolve().parents[4]


class OntoConfig(BaseSettings):
    """`ref_url` serves the agent, `val_url` the gate; `files` load in order — the schema, then the data."""

    model_config = SettingsConfigDict(env_prefix="DEEPTRACK_ONTO_", frozen=True)

    ref_url: str = "http://localhost:8080/mcp"
    val_url: str = "http://localhost:8081/mcp"
    token: SecretStr | None = None
    directory: Path = ROOT / "ontology"
    files: tuple[str, ...] = ("seguros.ttl", "datos.ttl")
    shapes: str = "formas.ttl"
