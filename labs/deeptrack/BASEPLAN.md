# Sistema multiagente de seguros: Deep Agents + Open Ontologies + Langfuse

Guía de montaje con todo lo acordado. No define la arquitectura del proyecto: solo cómo integrar y usar cada pieza.

> **Antes de empezar:** varios nombres de parámetros y herramientas cambian entre versiones. Donde aparece ⚠️, verificá contra la versión instalada (`pip show`, `get_tools()`, docs oficiales).

---

## 0. Principios rectores

1. **La IA propone, algo verifica.** Ninguna transacción se ejecuta solo porque el LLM lo decidió.
2. **Forzar con arquitectura, no con prompts.** La validación ontológica es un nodo determinista del grafo que el código ejecuta siempre. El agente no puede saltarlo porque no tiene la herramienta que ejecuta transacciones.
3. **State para decidir, eventos custom para mostrar.** El state guarda lo que el grafo necesita; la UI se alimenta de eventos con un contrato propio.
4. **Datos sensibles se enmascaran antes de salir** del backend (UI y trazas).
5. **Alguien de negocio es dueño de la ontología y de las formas SHACL.** Cada relación o regla nueva se aprueba explícitamente ("el join que nadie aprobó" es el error a evitar).

---

## 1. Dependencias

```bash
pip install deepagents langgraph langchain-mcp-adapters langfuse
# + el proveedor de modelo que uses (langchain-anthropic, langchain-openai, ...)
```

Open Ontologies (servidor MCP en Rust, un solo binario):

```bash
git clone https://github.com/fabio-rovai/open-ontologies
cd open-ontologies
cargo build --release
# binario en target/release/  ⚠️ verificar nombre exacto
```

Se arranca como servidor MCP con el subcomando `serve`. Sus herramientas llevan prefijo `onto_` (`onto_query`, `onto_shacl`, `onto_load`, `onto_clear`, `onto_validate`, `onto_stats`, ...).

Alternativa a evaluar: `open-ontologies-lite` (puente Python en PyPI sobre el mismo motor Oxigraph), si no querés compilar Rust.

---

## 2. Artefactos semánticos (los mantiene negocio + equipo técnico)

Dos archivos versionados en git:

- `ontologia/seguros.ttl`: clases y relaciones (Póliza, Asegurado, Siniestro, Cobertura, Endoso, Ramo, Productor...) y cómo se relacionan.
- `ontologia/formas.ttl`: reglas SHACL que toda transacción debe cumplir.

Ejemplos de reglas SHACL típicas:

- Un Siniestro tiene **exactamente una** Póliza (`sh:minCount 1`, `sh:maxCount 1`).
- La fecha de ocurrencia cae **dentro de la vigencia** de la póliza.
- El CUIT del asegurado tiene 11 dígitos (`sh:pattern "^[0-9]{11}$"`).
- Un Endoso no puede quitar una Cobertura con siniestro abierto.

```turtle
@prefix sh:  <http://www.w3.org/ns/shacl#> .
@prefix seg: <https://ejemplo.com/seguros#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

seg:SiniestroShape a sh:NodeShape ;
  sh:targetClass seg:Siniestro ;
  sh:property [ sh:path seg:poliza ; sh:class seg:Poliza ;
                sh:minCount 1 ; sh:maxCount 1 ] ;
  sh:property [ sh:path seg:fechaOcurrencia ; sh:datatype xsd:date ;
                sh:minCount 1 ] .

seg:AseguradoShape a sh:NodeShape ;
  sh:targetClass seg:Asegurado ;
  sh:property [ sh:path seg:cuit ; sh:pattern "^[0-9]{11}$" ;
                sh:minCount 1 ] .
```

Si conectás vocabularios externos (otros sistemas, estándares), tratá cada `skos:exactMatch` como una decisión a aprobar, no como algo obvio porque las etiquetas coinciden. Open Ontologies 2.0 rebaja equivalencias que no se sostienen, pero no puede confirmar que una sea correcta.

---

## 3. Conexión MCP: el detalle que rompe todo si se ignora

Open Ontologies guarda el grafo **en memoria**. Con `langchain-mcp-adapters`, `client.get_tools()` sin sesión abre un proceso nuevo por cada llamada a herramienta, así que **el store llega vacío cada vez**. Hay que usar una **sesión persistente** abierta durante toda la vida del proceso.

Además, se usan **dos instancias separadas**:

| Instancia | Contenido | Quién la usa | Herramientas |
|---|---|---|---|
| `onto_ref` | Ontología de referencia (solo lectura) | El agente | `onto_query`, `onto_stats` |
| `onto_val` | Ontología + propuesta a validar | Solo el código del gate | `onto_load`, `onto_shacl`, `onto_clear` |

Así el agente nunca puede vaciar ni ensuciar la ontología, y las validaciones no contaminan la referencia.

```python
from contextlib import AsyncExitStack
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

ONTO_BIN = "/opt/open-ontologies"  # ⚠️ ruta/nombre real

client = MultiServerMCPClient(
    {
        "onto_ref": {"command": ONTO_BIN, "args": ["serve"], "transport": "stdio"},
        "onto_val": {"command": ONTO_BIN, "args": ["serve"], "transport": "stdio"},
    }
)

stack = AsyncExitStack()


async def iniciar_ontologias():
    ref = await stack.enter_async_context(client.session("onto_ref"))
    val = await stack.enter_async_context(client.session("onto_val"))
    t_ref = {t.name: t for t in await load_mcp_tools(ref)}
    t_val = {t.name: t for t in await load_mcp_tools(val)}

    # ⚠️ revisar t.args_schema para los nombres reales de parámetros
    await t_ref["onto_load"].ainvoke({"path": "ontologia/seguros.ttl"})

    herramientas_agente = [t_ref["onto_query"], t_ref["onto_stats"]]
    return herramientas_agente, t_val
```

Reglas:

- **Lista blanca explícita** de herramientas para el agente. Nunca `onto_load`, `onto_clear` ni ninguna que escriba.
- Imprimí `[(t.name, t.args_schema) for t in tools]` al arrancar y ajustá los nombres de parámetros.
- Si corrés varios workers, cada uno con sus propias instancias.

---

## 4. Agentes con Deep Agents

Subagentes sugeridos (ajustar a tu dominio):

- **ontologo**: resuelve términos y relaciones consultando la ontología con SPARQL antes de que nadie toque datos. Evita joins inventados.
- **consultas**: responde preguntas sobre pólizas, coberturas y siniestros usando las relaciones que le dio el ontólogo.
- **transacciones**: arma propuestas de alta, endoso, denuncia de siniestro, etc. Solo **propone**.

```python
from deepagents import create_deep_agent

herramientas_agente, t_val = await iniciar_ontologias()

agente = create_deep_agent(
    model=MODELO,
    tools=[proponer_transaccion, *herramientas_negocio_lectura],
    system_prompt=PROMPT_ORQUESTADOR,  # ⚠️ en versiones viejas: instructions=
    subagents=[
        {
            "name": "ontologo",
            "description": "Resuelve términos y relaciones del dominio seguros",
            "system_prompt": PROMPT_ONTOLOGO,  # ⚠️ en versiones viejas: prompt=
            "tools": herramientas_agente,
        },
        {"name": "consultas", "description": "...", "system_prompt": "...", "tools": herramientas_negocio_lectura},
        {"name": "transacciones", "description": "...", "system_prompt": "...", "tools": [proponer_transaccion]},
    ],
)
```

Reglas:

- **Ningún agente ni subagente tiene herramientas que ejecuten** transacciones en el core asegurador.
- `proponer_transaccion` solo deja la propuesta en el state (clave `propuesta`). ⚠️ Para que una herramienta escriba en el state hay que devolver `Command(update=...)` con su `ToolMessage` y tener la clave declarada en el schema del agente; revisá cómo lo soporta tu versión de deepagents (state_schema o middleware).

---

## 5. El gate obligatorio de transacciones

El deep agent se monta como un nodo dentro de un grafo exterior de LangGraph:

```
agente → gate_shacl → aprobacion_humana → ejecutar
            ↑   │
            └───┘ (si hay violaciones, vuelve al agente con el informe)
```

```python
import asyncio
from langgraph.types import Command, interrupt

lock_val = asyncio.Lock()  # una validación a la vez por instancia onto_val


async def gate_shacl(state):
    if not state.get("propuesta"):
        return Command(goto="__end__")
    ttl = propuesta_a_turtle(state["propuesta"])  # tu conversor a RDF
    async with lock_val:
        await t_val["onto_clear"].ainvoke({})
        await t_val["onto_load"].ainvoke({"path": "ontologia/seguros.ttl"})
        await t_val["onto_load"].ainvoke({"turtle": ttl})  # ⚠️ params
        informe = await t_val["onto_shacl"].ainvoke({"shapes_path": "ontologia/formas.ttl"})  # ⚠️ params
    if hay_violaciones(informe):  # parsear el formato real del informe
        return Command(goto="agente", update={"errores_validacion": informe})
    return Command(goto="aprobacion_humana")


def aprobacion_humana(state):
    decision = interrupt({"propuesta": state["propuesta"]})
    return Command(goto="ejecutar" if decision == "aprobar" else "agente")
```

Reglas:

- `interrupt()` requiere **checkpointer** al compilar el grafo exterior (Postgres en producción).
- `ejecutar` es código determinista que llama al core; nunca el LLM.
- Poné un **límite de reintentos** gate → agente para evitar bucles.
- La validación SHACL **no reemplaza** las validaciones del core asegurador ni las exigencias regulatorias (SSN). Es una capa extra que atrapa errores del agente antes.

---

## 6. Streaming de eventos para la UI

### Qué va al state y qué a eventos

| Va al state | Va a eventos `custom` |
|---|---|
| Lo que otro nodo necesita leer | Progreso, estados intermedios, mensajes para el operador |
| Lo que debe sobrevivir a un `interrupt` (la propuesta pendiente) | Resultados a mostrar (se pueden emitir además de guardarlos) |

No metas datos solo de UI en el state: inflan los checkpoints y con `stream_mode="values"` mandarías el state entero (con datos personales) en cada paso.

### Emitir eventos desde nodos o herramientas

```python
from langgraph.config import get_stream_writer


def cotizar(state):
    w = get_stream_writer()
    w({"tipo": "progreso", "nodo": "cotizar", "pct": 30})
    prima = calcular(state["poliza"])
    w({"tipo": "resultado", "nodo": "cotizar", "prima": prima})
    return {"prima": prima}
```

### Consumir combinando modos

```python
async for ns, modo, ev in grafo.astream(
    entrada, config, subgraphs=True, stream_mode=["updates", "custom", "messages", "debug"]
):
    await publicar(ns, modo, enmascarar(ev))  # WebSocket o SSE
```

| Modo | Para qué |
|---|---|
| `updates` | Lo que devolvió cada nodo al terminar |
| `custom` | Eventos de UI emitidos con `get_stream_writer()` |
| `messages` | Tokens del LLM en streaming |
| `debug` (o `tasks`, según versión) | Inicio y fin de cada nodo: encender/apagar cajas del grafo |
| `subgraphs=True` | Cada evento trae namespace: sabés de qué subagente viene |

### Contrato de eventos

Definilo y documentalo; el frontend depende de esto, no del state:

```json
{"tipo": "progreso|resultado|nodo_inicio|nodo_fin|error|aprobacion_requerida",
 "nodo": "cotizar", "namespace": ["transacciones"], "run_id": "...",
 "timestamp": "2026-11-03T12:00:00Z", "payload": {}}
```

`enmascarar()` en el backend elimina o tapa DNI, CUIT, datos médicos y bancarios antes de que nada llegue al navegador.

---

## 7. Langfuse (trazas e histórico, autoalojado)

Licencia MIT, self-host gratuito con prácticamente todas las funciones.

### Levantar

```bash
git clone https://github.com/langfuse/langfuse.git
cd langfuse
docker compose up -d     # desarrollo; en producción, Helm
```

Crear proyecto en la UI y obtener claves:

```bash
export LANGFUSE_PUBLIC_KEY=pk-...
export LANGFUSE_SECRET_KEY=sk-...
export LANGFUSE_HOST=http://localhost:3000   # ⚠️ en SDKs nuevos: LANGFUSE_BASE_URL
```

### Instrumentar

```python
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler   # ⚠️ ruta según versión del SDK

Langfuse(mask=enmascarar_traza)   # enmascara PII antes de enviar
handler = CallbackHandler()

config = {"configurable": {"thread_id": tid}, "callbacks": [handler]}
async for ... in grafo.astream(entrada, config, ...):
    ...
```

Qué esperar:

- **Vista de grafo** por traza (beta): modo Agregado (forma general) y Expandido (ejecución paso a paso, bucles desplegados). Los subagentes aparecen anidados bajo su padre.
- **No es en vivo**: las trazas llegan en lotes, segundos después.
- Muestra **lo que se ejecutó**, no el grafo diseñado con todas sus rutas posibles.
- No permite pausar ni editar estado.

---

## 8. Visualización en vivo

### Desarrollo: LangGraph Studio

- Requiere `langgraph.json` en el proyecto y `langgraph dev`.
- El servidor corre local; la interfaz se abre desde la web de LangSmith (cuenta gratuita).
- **Solo con datos ficticios.** LangSmith/Studio autoalojado exige plan Enterprise.
- Los subagentes de Deep Agents no aparecen como nodos expandibles en el dibujo (se invocan desde una herramienta); se ven en el panel de ejecución.

### Producción: visor propio ("Studio casero")

1. Estructura del grafo diseñado: `grafo.get_graph(xray=True).to_json()` (o `.draw_mermaid()`).
2. Renderizarla en el frontend (React Flow o similar).
3. Con los eventos de la sección 6: `nodo_inicio`/`nodo_fin` encienden y apagan nodos; `custom` muestra progreso y resultados.
4. Para Deep Agents, el SDK de frontend de LangChain (`useStream`) expone `stream.subagents` y la lista de tareas en tiempo real.

Combinación final: **visor propio para el vivo, Langfuse para el histórico, Studio solo en desarrollo.**

---

## 9. Checklist

- [ ] Open Ontologies compilado; nombres de herramientas y parámetros verificados con `args_schema`.
- [ ] Sesiones MCP **persistentes** (no `get_tools()` sin sesión).
- [ ] Dos instancias: `onto_ref` (agente, solo lectura) y `onto_val` (gate, con lock).
- [ ] `seguros.ttl` y `formas.ttl` en git, con dueño de negocio que aprueba cambios.
- [ ] Ningún agente tiene herramientas que ejecuten transacciones.
- [ ] Gate SHACL + `interrupt()` + checkpointer + límite de reintentos.
- [ ] Contrato de eventos documentado; enmascarado de PII en UI y en Langfuse.
- [ ] Langfuse autoalojado con claves por entorno.
- [ ] Studio solo con datos ficticios.
- [ ] Validaciones del core y regulatorias se mantienen independientes de esta capa.
