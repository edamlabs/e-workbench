"""logic.agent: InsuranceAgent — the deep agent: an orchestrator and three subagents, each holding only its role's tools.

`ontologo` resolves terms and relations against the reference ontology (SPARQL, read-only); `consultas` reads one
policy through a fixed, parameterized query — never free SPARQL over the data; `transacciones` proposes and
nothing else. No agent holds a tool that executes: execution is a node of the outer graph, behind the gate."""

from typing import Final

import msgspec
from deepagents import create_deep_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import StructuredTool
from langgraph.graph.state import CompiledStateGraph

from deeptrack.logic.ports import OntoPort
from deeptrack.logic.proposal import ProposalMiddleware
from deeptrack.logic.state import ChatState
from deeptrack.models.proposal import LocalName

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

TRANSACCIONES: Final[str] = """Eres el gestor de transacciones. Solo propones: `proponer_denuncia` o `proponer_endoso`,
con nombres locales exactos (pol-1001, cob-robo) y fechas ISO. Nunca afirmas que algo se ejecutó."""

POLICY: Final[str] = """PREFIX seg: <https://deeptrack.lab/seguros#>
SELECT ?asegurado ?ramo ?desde ?hasta ?cobertura ?siniestro ?abierto WHERE {{
  seg:{name} a seg:Poliza ; seg:asegurado/seg:nombre ?asegurado ; seg:ramo/seg:nombre ?ramo ;
             seg:vigenciaDesde ?desde ; seg:vigenciaHasta ?hasta .
  OPTIONAL {{ seg:{name} seg:cubre/seg:nombre ?cobertura }}
  OPTIONAL {{ ?s seg:poliza seg:{name} ; seg:abierto ?abierto . BIND(STRAFTER(STR(?s), "#") AS ?siniestro) }}
}}"""


class InsuranceAgent:
    """The deep agent over a chat model and the ontology port."""

    __slots__ = ("_model", "_onto")

    def __init__(self, model: BaseChatModel, onto: OntoPort) -> None:
        self._model = model
        self._onto = onto

    ############################################################

    async def policy(self, poliza: str) -> str:
        """Lee una póliza por su nombre local (p. ej. pol-1001): asegurado, ramo, vigencia, coberturas y siniestros."""
        return await self._onto.query(POLICY.format(name=msgspec.convert(poliza, LocalName)))

    def build(self) -> CompiledStateGraph:
        """The compiled deep agent, ready to mount as the outer graph's `agent` node."""
        consult = StructuredTool.from_function(coroutine=self.policy, name="consultar_poliza", handle_tool_error=True)
        return create_deep_agent(
            model=self._model,
            system_prompt=PROMPT,
            state_schema=ChatState,
            name="agent",
            subagents=[
                {
                    "name": "ontologo",
                    "description": "Resuelve términos y relaciones del dominio seguros contra la ontología.",
                    "system_prompt": ONTOLOGO,
                    "tools": list(self._onto.tools),
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
                    "tools": [],
                    "middleware": [ProposalMiddleware()],
                },
            ],
        )
