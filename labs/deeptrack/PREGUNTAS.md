# Preguntas de prueba — flujo completo

UI: http://localhost:28104 · Langfuse: http://localhost:28100 (`admin@labs.local`, contraseña en `.env` →
`LABS_LANGFUSE_USER_PASSWORD`; proyecto `labs-deeptrack`, entorno `labs`; las trazas tardan ~5 s).

Datos ficticios (`ontology/datos.ttl`): `pol-1001` automotor, vigente 2026, cubre RC (`cob-rc`) y robo (`cob-robo`),
siniestro `sin-0001` abierto sobre robo · `pol-2002` hogar, vigente 2025-03-01 → 2026-02-28, cubre incendio.

## 1 · Consulta

```text
¿Qué coberturas tiene la póliza pol-1001 y tiene siniestros abiertos?
```

Esperado: `task` → `consultas` → `consultar_poliza` → MCP `onto_query`. Responsabilidad civil y Robo total; `sin-0001`
abierto.

## 2 · Ontología

```text
¿Cómo se relaciona un siniestro con una póliza y qué atributos tiene un endoso?
```

Esperado: `task` → `ontologo` → `onto_query` (SPARQL sobre la ontología de referencia). Siniestro → `seg:poliza` → Póliza;
Endoso → `seg:endosa` (póliza) y `seg:quita` (cobertura).

## 3 · Denuncia válida → aprobar

```text
Quiero denunciar un siniestro de responsabilidad civil en la póliza pol-1001 ocurrido el 2026-07-01
```

Esperado: `transacciones` → `proponer_denuncia` → gate SHACL (MCP `onto_clear` / `onto_load` / `onto_shacl`) → tarjeta de
aprobación en el chat. **Aprobar** → «Transacción registrada (stub, sin core)».

## 4 · Denuncia válida → rechazar

```text
Quiero denunciar un siniestro de responsabilidad civil en la póliza pol-1001 ocurrido el 2026-07-02
```

Esperado: igual que la 3 hasta la tarjeta. **Rechazar** → vuelve al agente, que confirma que no se registra.

## 5 · Fuera de vigencia (SHACL `sh:sparql`)

```text
Denuncia un incendio en la póliza pol-2002 ocurrido el 2026-07-01
```

Esperado: el gate rechaza («La fecha de ocurrencia cae fuera de la vigencia de la póliza»), el informe vuelve al agente
y este explica por qué no procede. No hay tarjeta de aprobación.

## 6 · Endoso con siniestro abierto (SHACL `sh:sparql`)

```text
Quita la cobertura de robo total de la póliza pol-1001
```

Esperado: `proponer_endoso` → el gate rechaza («El endoso quita una cobertura con un siniestro abierto»).

## 7 · Enmascarado de datos personales

```text
El asegurado con CUIT 20-11111111-2 pregunta qué cubre su póliza pol-1001
```

Esperado: en Langfuse y en la consola de `make dev` el CUIT aparece como `[CUIT]`.
