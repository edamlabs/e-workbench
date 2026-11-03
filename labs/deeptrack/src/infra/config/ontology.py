"""infra/config/ontology: the lab's ontology files — the schema and data the reference holds, the shapes the gate judges by."""

from pathlib import Path
from typing import Final

from pydantic_settings import SettingsConfigDict

from infra.config.base import BaseSettings

ROOT: Final[Path] = Path(__file__).resolve().parents[3]


class OntologySettings(BaseSettings):
    """`files` load in order — the schema, then the data; `shapes` is the SHACL every proposal crosses."""

    model_config = SettingsConfigDict(env_prefix="DEEPTRACK_ONTOLOGY_")

    directory: Path = ROOT / "ontology"
    files: tuple[str, ...] = ("seguros.ttl", "datos.ttl")
    shapes: str = "formas.ttl"

    @property
    def texts(self) -> tuple[str, ...]:
        """The schema and data, in load order."""
        return tuple((self.directory / name).read_text() for name in self.files)

    @property
    def shapes_text(self) -> str:
        """The SHACL shapes."""
        return (self.directory / self.shapes).read_text()
