"""infra/config/ontology: the lab's ontology files — the schema and data the reference holds, the shapes the gate judges by."""

from pathlib import Path

from infra.config.base import LAB, BaseSettings


##### SETTINGS #####
class OntologySettings(BaseSettings):
    """The files load in order — the schema, then the data; the shapes are the SHACL every proposal crosses."""

    ### ONTOLOGY
    DEEPTRACK_ONTOLOGY_DIRECTORY: Path = LAB / "ontology"
    DEEPTRACK_ONTOLOGY_FILES: tuple[str, ...] = ("seguros.ttl", "datos.ttl")
    DEEPTRACK_ONTOLOGY_SHAPES: str = "formas.ttl"

    @property
    def ontology_texts(self) -> tuple[str, ...]:
        """The schema and data, in load order."""
        return tuple((self.DEEPTRACK_ONTOLOGY_DIRECTORY / name).read_text() for name in self.DEEPTRACK_ONTOLOGY_FILES)

    @property
    def ontology_shapes(self) -> str:
        """The SHACL shapes."""
        return (self.DEEPTRACK_ONTOLOGY_DIRECTORY / self.DEEPTRACK_ONTOLOGY_SHAPES).read_text()
