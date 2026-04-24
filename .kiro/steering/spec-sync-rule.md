---
inclusion: always
---

# Regla de Sincronización de Specs — MEPIA

## Regla de Oro

**Todo cambio de código, contrato de API, modelo de datos o lógica de negocio DEBE reflejarse
en el archivo de spec correspondiente antes de considerarse completo.**

No existe código "correcto" que no esté documentado en su spec.

---

## Qué actualizar y dónde

| Tipo de cambio                          | Archivo(s) a actualizar                                      |
|-----------------------------------------|--------------------------------------------------------------|
| Nuevo endpoint REST                     | Spec del nodo correspondiente (`n0X_*.md`) + `_index.md`     |
| Cambio en modelo Pydantic               | Spec del nodo + `_glossary.md` si es contrato compartido     |
| Nueva tabla o columna en DB             | `db_schema.md` + spec del nodo que la usa                    |
| Nuevo contrato de datos (input/output)  | `_glossary.md` sección "Contratos de datos"                  |
| Cambio en lógica de Gatekeeper (S2)     | `s2_gatekeeper.md` catálogo de métricas                      |
| Nueva función de cálculo (S3)           | `s3_motor_calculo.md` + prerequisitos en `s2_gatekeeper.md`  |
| Nuevo agente o nodo                     | Archivo nuevo `nXX_*.md` + fila en tabla de `_index.md`      |
| Cambio en umbrales de alerta            | `s3_motor_calculo.md` tabla de umbrales                      |
| Cambio en arquetipos o prompt templates | `s4_auditoria_ia.md`                                         |
| Nuevo término de dominio                | `_glossary.md`                                               |

---

## Protocolo por sesión

Al inicio de cada sesión de desarrollo:
1. Leer `_index.md` para entender el estado actual del pipeline
2. Leer el spec del nodo en el que se va a trabajar
3. Leer `_glossary.md` si se van a usar o crear contratos de datos

Al finalizar cada tarea de implementación:
1. Actualizar el spec del nodo con los cambios realizados
2. Si se creó un contrato nuevo → agregarlo a `_glossary.md`
3. Si se creó un nodo nuevo → agregar fila en `_index.md` con estado `✅ req done`
4. Si se modificó el schema → actualizar `db_schema.md`

---

## Formato de estado en `_index.md`

| Símbolo       | Significado                              |
|---------------|------------------------------------------|
| `pendiente`   | Spec no iniciado                         |
| `✅ req done` | Requerimientos documentados              |
| `🔧 in dev`   | En implementación activa                 |
| `✅ done`     | Implementado + spec sincronizado         |

---

## Regla de no-avance

No se avanza al siguiente nodo del pipeline si el spec del nodo actual tiene discrepancias
conocidas con el código implementado. Las discrepancias se documentan explícitamente en el
spec bajo una sección `## Discrepancias conocidas` hasta que se resuelvan.

---

## Estructura de archivos de spec — Límite de 500 palabras

**Todo archivo `.md` de spec en `.kiro/specs/mepia/` debe respetar estas reglas:**

### Límite estricto
- Máximo 500 palabras **por archivo** — no por nodo
- El detalle nunca se recorta: si se necesita más espacio, se divide en archivos hermanos
- Un nodo puede tener N archivos, cada uno ≤ 500 palabras
- El archivo principal del nodo es el índice del nodo: resume y referencia a los hermanos

### Convención de nombres para archivos hermanos

```
nXX_nombre.md                ← archivo principal (resumen + referencias)
nXX_nombre_formulas.md       ← fórmulas y lógica matemática detallada
nXX_nombre_examples.md       ← ejemplos de payload / casos de uso
nXX_nombre_edge_cases.md     ← casos de borde extensos
nXX_nombre_contracts.md      ← contratos de datos específicos del nodo
```

El archivo principal SIEMPRE incluye al final una sección:
```
## Archivos relacionados de este nodo
- `nXX_nombre_formulas.md` — cargar para implementar cálculos
- `nXX_nombre_examples.md` — cargar para escribir tests
```

Así el agente sabe exactamente qué cargar según la tarea.

### Estructura obligatoria de cada archivo de nodo

```
# [ID] — [Nombre del Nodo]

**Capa:** [Sequential|Parallel|Loop] | **Anterior:** [nodo] | **Siguiente:** [nodo]
**Archivos relacionados:** [lista corta]

## Input / Output          ← máx 5 líneas
## User Stories            ← máx 4 historias, 1 línea cada una
## Acceptance Criteria     ← formato WHEN/THEN, máx 8 criterios
## Edge Cases              ← máx 5 casos, 1 línea cada uno
```

### Archivos de infraestructura (`_index.md`, `_glossary.md`, `db_schema.md`)
- `_index.md`: solo el mapa del pipeline + tabla de nodos + reglas de carga. Sin detalles de implementación.
- `_glossary.md`: solo definiciones y contratos. Sin lógica de negocio.
- `db_schema.md`: solo DDL conceptual (tablas, columnas, tipos, índices). Sin flujos ni criterios.

### Regla de carga de contexto por sesión
Al implementar un nodo, cargar SOLO:
1. `_index.md` + `_glossary.md` (siempre)
2. El archivo del nodo específico
3. Archivos `_detail.md` o `_examples.md` solo si son necesarios para la tarea

**NO cargar todos los archivos de nodos simultáneamente.**
