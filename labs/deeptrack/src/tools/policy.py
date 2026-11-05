"""tools/policy: PolicyTool — `consultar_poliza`, one policy read through a fixed, parameterized query, never free SPARQL.

The name is checked as a local name before it reaches the query; a name that is not one is a `ToolException` the model
reads and corrects. The query returns local names (`cob-rc`) beside the labels: what the proposing tools take is
exactly what this returns."""

from typing import Final

import msgspec
from beartype import beartype
from langchain_core.tools import BaseTool, StructuredTool, ToolException

from models.proposal import LocalName
from ports.ontology import OntologyPort

NAME: Final[str] = "consultar_poliza"
QUERY: Final[str] = """PREFIX seg: <https://deeptrack.lab/seguros#>
SELECT ?asegurado ?ramo ?desde ?hasta ?cobertura ?coberturaNombre ?siniestro ?siniestroCobertura ?abierto WHERE {{
  seg:{name} a seg:Poliza ; seg:asegurado/seg:nombre ?asegurado ; seg:ramo/seg:nombre ?ramo ;
             seg:vigenciaDesde ?desde ; seg:vigenciaHasta ?hasta .
  OPTIONAL {{ seg:{name} seg:cubre ?c . ?c seg:nombre ?coberturaNombre . BIND(STRAFTER(STR(?c), "#") AS ?cobertura) }}
  OPTIONAL {{
    ?s seg:poliza seg:{name} ; seg:abierto ?abierto ; seg:cobertura ?sc .
    BIND(STRAFTER(STR(?s), "#") AS ?siniestro) BIND(STRAFTER(STR(?sc), "#") AS ?siniestroCobertura)
  }}
}}"""


@beartype
class PolicyTool:
    """The policy reader over the reference ontology server."""

    __slots__ = ("_reference",)

    def __init__(self, reference: OntologyPort) -> None:
        self._reference = reference

    ############################################################

    async def run(self, poliza: str) -> str:
        """Lee una póliza por su nombre local (p. ej. pol-1001): asegurado, ramo, vigencia, coberturas (nombre local y
        etiqueta) y siniestros con la cobertura afectada."""
        try:
            name = msgspec.convert(poliza, LocalName)
        except msgspec.ValidationError as error:
            msg = f"«{poliza}» no es un nombre local de póliza: usa la forma pol-1001."
            raise ToolException(msg) from error
        return await self._reference.call("onto_query", {"query": QUERY.format(name=name)})

    @property
    def tool(self) -> BaseTool:
        """The tool the agents name `consultar_poliza`."""
        return StructuredTool.from_function(coroutine=self.run, name=NAME, handle_tool_error=True)
