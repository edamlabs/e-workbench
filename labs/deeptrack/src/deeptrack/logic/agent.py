"""logic/agent: InsuranceAgent — the deep agent: an orchestrator and three subagents, each holding only its role's tools.

`ontologo` resolves terms and relations against the reference ontology (SPARQL, read-only); `consultas` reads one
policy through a fixed, parameterized query — never free SPARQL over the data; `transacciones` proposes and
nothing else. No agent holds a tool that executes: execution is a node of the outer graph, behind the gate."""

from typing import Final

import msgspec
from deepagents import SubAgent, create_deep_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import StructuredTool, ToolException
from langgraph.graph.state import CompiledStateGraph

from deeptrack.logic.proposal import ProposalMiddleware
from deeptrack.logic.state import ChatState
from deeptrack.models.proposal import LocalName
from engines.shacl import ShaclValidation
from ports.ontology import OntologyPort

### the ontologist's whitelist over the reference server: it reads, it never loads.
READ_TOOLS: Final[tuple[str, ...]] = ("onto_query", "onto_stats")

PROMPT: Final[str] = """Eres el orquestador de un asistente de seguros. Delegas con la herramienta `task`:
- `ontologo` antes de usar un término o relación del dominio que no tengas resuelto: no inventes relaciones.
- `consultas` para leer pólizas, coberturas y siniestros.
- `transacciones` para proponer una denuncia de siniestro o un endoso. Nadie ejecuta: la propuesta pasa por una
  validación automática y por la aprobación de un operador.
Si recibes un informe de validación con violaciones, corrige la propuesta o explica al usuario por qué no procede.
Responde en español, breve y exacto."""

ONTOLOGO: Final[str] = """Eres el ontólogo. Resuelves términos y relaciones del dominio seguros consultando la ontología
de referencia con SPARQL (`onto_query`, prefijo seg: <https://deeptrack.lab/seguros#>). Devuelves las clases y
propiedades exactas (nombre local y significado). Nunca supones una relación que la ontología no declara."""

CONSULTAS: Final[str] = """Eres el analista de consultas. Lees una póliza con `consultar_poliza` (nombre local, p. ej.
pol-1001) y respondes con lo que devuelve: asegurado, ramo, vigencia, coberturas y siniestros. No inventas datos."""

TRANSACCIONES: Final[str] = """Eres el gestor de transacciones. Solo propones: `proponer_denuncia` o `proponer_endoso`.
Antes de proponer, lee la póliza con `consultar_poliza` y usa exactamente los nombres locales que devuelve (columna
`cobertura`, p. ej. cob-rc; nunca la etiqueta) y fechas ISO. Si una herramienta devuelve un error, corrige y reintenta.
Nunca afirmas que algo se ejecutó."""

### local names (`cob-rc`) beside the labels: what the proposing tools take is exactly what this returns.
POLICY: Final[str] = """PREFIX seg: <https://deeptrack.lab/seguros#>
SELECT ?asegurado ?ramo ?desde ?hasta ?cobertura ?coberturaNombre ?siniestro ?siniestroCobertura ?abierto WHERE {{
  seg:{name} a seg:Poliza ; seg:asegurado/seg:nombre ?asegurado ; seg:ramo/seg:nombre ?ramo ;
             seg:vigenciaDesde ?desde ; seg:vigenciaHasta ?hasta .
  OPTIONAL {{ seg:{name} seg:cubre ?c . ?c seg:nombre ?coberturaNombre . BIND(STRAFTER(STR(?c), "#") AS ?cobertura) }}
  OPTIONAL {{
    ?s seg:poliza seg:{name} ; seg:abierto ?abierto ; seg:cobertura ?sc .
    BIND(STRAFTER(STR(?s), "#") AS ?siniestro) BIND(STRAFTER(STR(?sc), "#") AS ?siniestroCobertura)
  }}
}}"""


class InsuranceAgent:
    """The deep agent over a chat model and the reference ontology server."""

    __slots__ = ("_model", "_ontologist", "_reference", "_validator")

    def __init__(
        self,
        model: BaseChatModel,
        reference: OntologyPort,
        *,
        ontologist: bool = True,
        validator: ShaclValidation | None = None,
    ) -> None:
        self._model = model
        self._reference = reference
        self._ontologist = ontologist
        self._validator = validator

    ############################################################

    async def policy(self, poliza: str) -> str:
        """Lee una póliza por su nombre local (p. ej. pol-1001): asegurado, ramo, vigencia, coberturas (nombre local y
        etiqueta) y siniestros con la cobertura afectada."""
        try:
            name = msgspec.convert(poliza, LocalName)
        except msgspec.ValidationError as error:
            msg = f"«{poliza}» no es un nombre local de póliza: usa la forma pol-1001."
            raise ToolException(msg) from error
        return await self._reference.call("onto_query", {"query": POLICY.format(name=name)})

    def subagents(self) -> list[SubAgent]:
        """The three roles, each with exactly its tools: the ontologist reads the ontology, the analyst reads one policy,
        the transactions manager reads one policy and proposes."""
        consult = StructuredTool.from_function(coroutine=self.policy, name="consultar_poliza", handle_tool_error=True)
        reading = [self._reference.tools[name] for name in READ_TOOLS if name in self._reference.tools]
        roles: list[SubAgent] = [
            {
                "name": "ontologo",
                "description": "Resuelve términos y relaciones del dominio seguros contra la ontología.",
                "system_prompt": ONTOLOGO,
                "tools": reading,
            },
            {
                "name": "consultas",
                "description": "Lee pólizas, coberturas y siniestros.",
                "system_prompt": CONSULTAS,
                "tools": [consult],
            },
            {
                "name": "transacciones",
                "description": "Propone denuncias de siniestro y endosos; nunca ejecuta.",
                "system_prompt": TRANSACCIONES,
                "tools": [consult],
                "middleware": [ProposalMiddleware(self._validator)],
            },
        ]
        ### the arms without the ontologist drop the role whole: the orchestrator is told of the rest only.
        return [role for role in roles if self._ontologist or role["name"] != "ontologo"]

    def build(self) -> CompiledStateGraph:
        """The compiled deep agent, ready to mount as the outer graph's `agent` node."""
        return create_deep_agent(
            model=self._model, system_prompt=PROMPT, state_schema=ChatState, name="agent", subagents=self.subagents()
        )
