# N11 — Consultor Especialista (Core Auditor LLM)

**Capa:** Layer 3 — Nodo 2 | **Anterior:** N10 Context Builder | **Siguiente:** N12 Phrase Expander
**Archivo de implementación:** `agents/core_auditor.py`
**Tipo:** LLM Principal (Heavy-lifter)
**Archivos relacionados:** `n10_context_builder.md`, `n12_phrase_expander.md`, `_glossary.md`

---

## Sección 1 — Misión y Tipo de Nodo

**Tipo:** LLM Principal (Heavy-lifter) — genera texto, no transforma datos.

**Misión:** Recibir el `EnrichedAuditPayload` desde N10, cruzar los insights matemáticos
(generados en capas previas por S4 y N05) contra el contexto histórico y la identidad de
marca, y redactar un borrador de auditoría completo (`Draft_Report`).

No hace interpretación de datos plana. Genera frases conversacionales e insights accionables
y físicos para dueños de negocios de hospitalidad. Su salida es evaluada por N12 (Phrase Expander)
y N13 (Quality Reviewer) antes de llegar al dueño.

```
N10 EnrichedAuditPayload
        │
        ↓
N11 Consultor Especialista (LLM)
  ├─ Lee time_series → determina enfoque por temporalidad
  ├─ Lee forensic_report + audit_insights → hallazgos técnicos crudos
  ├─ Lee brand_identity → aplica Lente del CEO (tono y límites)
  ├─ Lee historical_context → causa probable antes de asumir error humano
  └─ Redacta Draft_Report
        │
        ↓
N12 Phrase Expander
```

---

## Sección 2 — Mapeo de Temporalidad (Chain of Thought Dinámico)

N11 ajusta su enfoque analítico según el campo `temporalidad` del `EnrichedAuditPayload`.
Los tres modos mapean exactamente al enum `Literal["short", "medium", "long"]`.

### `short` — últimos 30 días

**Enfoque:** Fricción inmediata y operación diaria.

Preguntas que guían el análisis:
- ¿Hubo cierres de caja con varianza negativa esta semana?
- ¿Hay mermas puntuales en insumos de alto costo (café, lácteos)?
- ¿El rendimiento por turno muestra caídas atípicas?
- ¿El desgaste del equipo humano se refleja en tickets promedio bajos en ciertos horarios?
- ¿La calibración diaria del equipo (dial-in, temperatura) está generando desperdicio?

**Tono del reporte:** Urgente pero calmado. Acciones para mañana.

---

### `medium` — últimos 6 meses

**Enfoque:** Tendencias de mediano plazo y eficiencia del menú.

Preguntas que guían el análisis:
- ¿Qué productos del menú están perdiendo velocidad de venta?
- ¿El ticket promedio está subiendo o bajando? ¿Por qué?
- ¿Hay cambios en hábitos de consumo (horarios, categorías)?
- ¿La rotación estacional de insumos está generando merma por vencimiento?
- ¿La ingeniería del menú actual sigue siendo rentable?

**Tono del reporte:** Reflexivo. Patrones, no emergencias.

---

### `long` — último año

**Enfoque:** Salud financiera estructural y desgaste físico.

Preguntas que guían el análisis:
- ¿La tendencia anual de margen es positiva, estable o en deterioro?
- ¿Los proveedores actuales siguen siendo competitivos? ¿Es momento de renegociar?
- ¿El desgaste físico de maquinaria pesada (molinos, máquinas de espresso) se refleja en
  incremento de merma o caída de calidad?
- ¿La salud financiera general permite inversión en CapEx o requiere contención?
- ¿Hay estacionalidad clara que deba anticiparse para el siguiente ciclo?

**Tono del reporte:** Estratégico. Visión de negocio, no operación diaria.

---

## Sección 3 — Estructura Exacta de Entrada y Salida

### Entrada — `EnrichedAuditPayload` (output de N10)

N11 lee los siguientes campos del payload:

```python
# Temporalidad — determina el modo de análisis
temporalidad = payload.temporalidad          # "short" | "medium" | "long"
time_series  = payload.time_series           # rollups SQL por granularidad

# Hallazgos técnicos crudos
forensic_report  = payload.forensic_report   # ForensicReport de S4 — anomalías y riesgos
audit_insights   = payload.audit_insights    # AuditInsight[] de N05 — insights CEO-framed

# Identidad de marca — tono y límites
brand_identity   = payload.brand_identity    # BrandIdentityBlock — Lente del CEO

# Memoria histórica — contexto de equipos y patrones recurrentes
historical_context = payload.historical_context  # string RAG consolidado (máx 1,500 tokens)

# Contexto operativo del día
parallel_summary = payload.parallel_summary  # estado de N09 (gastos) y nodos paralelos
```

> Nota: `forensic_report` proviene de **S4 Forensic CFO**, no de N07.
> N07 está marcado como `skipped_v1` y no existe en esta versión.

---

### Salida — `Draft_Report`

```python
class PragmaticAction(BaseModel):
    action: str              # descripción de la acción — lenguaje directo, sin jerga
    priority: Literal["immediate", "this_week", "this_month"]
    owner: str               # quién debe ejecutarla (ej. "barista líder", "dueño")


class DraftReport(BaseModel):
    # Trazabilidad
    layer3_run_id: UUID      # mismo UUID del EnrichedAuditPayload de N10
    business_id: UUID
    date: date
    archetype: Literal["Operative Genius", "Product Purist", "Growth Hacker"]
    temporalidad: Literal["short", "medium", "long"]

    # Contenido del reporte
    executive_summary: str           # 1–2 frases directas al dueño sobre la salud del período
    operational_narrative: str       # hallazgos traducidos a realidades físicas
    pragmatic_actions: list[PragmaticAction]  # 1–3 acciones, nunca más

    # Metadata de generación
    model_used: str          # ej. "gpt-4o", "claude-3-5-sonnet"
    generated_at: datetime
    generation_duration_ms: int
    draft_status: Literal["draft"]   # siempre "draft" — N12/N13 lo validan
```

**Reglas de contenido:**

| Campo | Regla |
|-------|-------|
| `executive_summary` | Máx 2 frases. Menciona el período y el estado general. Sin jerga. |
| `operational_narrative` | Basado en `time_series` + `forensic_report`. Traduce números a realidades físicas. |
| `pragmatic_actions` | Mínimo 1, máximo 3. Cada una con `priority` y `owner` explícitos. |

---

## Sección 4 — System Prompt Base (El Motor de los Lentes)

```
Eres el Consultor Especialista de MEPIA, un operador de piso experto en cafeterías de
especialidad con 15 años de experiencia en operaciones de hospitalidad.

Tu trabajo en esta sesión es redactar un borrador de auditoría financiera y operativa
para el dueño de un negocio de hospitalidad. Recibirás datos matemáticos ya procesados
y tu trabajo es traducirlos a realidades físicas y acciones concretas.

═══════════════════════════════════════════════════════
DIRECTIVA 1 — LENTE OPERATIVO (EL PISO)
═══════════════════════════════════════════════════════
Traduce los "audit_insights" y el "forensic_report" a realidades físicas.
No digas "el margen bajó 10%". Di "eso equivale a 3 kilos de café desperdiciado
o 40 bebidas que salieron sin cobrar correctamente".
Piensa en purgas, mal dial-in, cuellos de botella en barra, desgaste de equipo
humano en turno tarde, compras de emergencia que rompen el costo estándar.

═══════════════════════════════════════════════════════
DIRECTIVA 2 — REGLA DE ORO (ANCLAJE RAG)
═══════════════════════════════════════════════════════
Antes de redactar la "operational_narrative", lee la sección "brand_identity".
Cualquier recomendación DEBE alinearse con las reglas del dueño ahí descritas.
Si las reglas de brand_identity contradicen tu conocimiento general de operaciones,
OBEDECES a la brand_identity. Siempre.
Ejemplo: si brand_identity prohíbe tácticas de fidelización agresivas, no las sugieras
aunque los datos muestren caída en recompra.

═══════════════════════════════════════════════════════
DIRECTIVA 3 — CONTINUIDAD HISTÓRICA
═══════════════════════════════════════════════════════
Si existe un "historical_context" relacionado con equipo físico o infraestructura
(molino, máquina de espresso, refrigeración), úsalo como causa probable para explicar
anomalías actuales ANTES de asumir errores humanos.
El equipo falla antes que las personas. Documenta esa hipótesis primero.

═══════════════════════════════════════════════════════
DIRECTIVA 4 — PROHIBICIÓN DE ESTILO
═══════════════════════════════════════════════════════
PROHIBIDO usar lenguaje corporativo o de consultor tradicional.
Palabras y frases prohibidas: "optimizar recursos", "sinergia", "KPIs", "roadmap",
"stakeholders", "apalancar", "deep dive", "best practices".
Habla de frente, con humildad y empatía. Como un colega que conoce el negocio,
no como un consultor que factura por hora.
El dueño debe sentir que alguien que entiende su cocina le está hablando.

═══════════════════════════════════════════════════════
FORMATO DE SALIDA OBLIGATORIO
═══════════════════════════════════════════════════════
Responde ÚNICAMENTE con un JSON válido con esta estructura exacta:
{
  "executive_summary": "string — máx 2 frases",
  "operational_narrative": "string — hallazgos físicos y contextuales",
  "pragmatic_actions": [
    {
      "action": "string",
      "priority": "immediate | this_week | this_month",
      "owner": "string"
    }
  ]
}
No incluyas texto fuera del JSON. No uses markdown dentro del JSON.
```

---

## Endpoint REST

### `POST /layer3/consult`

Llamado internamente por N10 tras persistir el `EnrichedAuditPayload`.

**Request body:**
```python
class ConsultInput(BaseModel):
    enriched_payload: EnrichedAuditPayload   # output completo de N10
```

**Response 200:**
```json
{
  "layer3_run_id": "uuid-v4",
  "draft_status": "draft",
  "generated_at": "2024-01-15T22:18:00Z",
  "generation_duration_ms": 4200
}
```

**Códigos de error:**

| HTTP | Condición |
|------|-----------|
| 422  | `EnrichedAuditPayload` inválido o incompleto |
| 503  | LLM no disponible o timeout |
| 409  | Ya existe un `Draft_Report` para este `layer3_run_id` — idempotencia |

---

## Persistencia en `audit_results`

N11 persiste el `Draft_Report` antes de entregarlo a N12.

| Campo           | Valor |
|-----------------|-------|
| `run_id`        | `layer3_run_id` (mismo de N10) |
| `business_id`   | FK → businesses |
| `date`          | Fecha auditada |
| `pipeline_layer`| `"loop"` |
| `node_id`       | `"N11"` |
| `module`        | `"core_auditor"` |
| `archetype`     | Arquetipo del run |
| `raw_result`    | `DraftReport` serializado (JSON) |
| `copilot_phrase`| `executive_summary` del `DraftReport` |
| `node_status`   | `"success"` \| `"failed"` |

---

## Acceptance Criteria

- WHEN `temporalidad == "short"` → `operational_narrative` enfocado en fricción diaria y cierres de caja
- WHEN `temporalidad == "medium"` → `operational_narrative` enfocado en tendencias de menú y ticket promedio
- WHEN `temporalidad == "long"` → `operational_narrative` enfocado en salud financiera y desgaste de maquinaria
- WHEN `brand_identity.retrieved: true` → todas las `pragmatic_actions` respetan las reglas de marca
- WHEN `historical_context` contiene mención de equipo físico → N11 lo usa como causa probable antes de asumir error humano
- WHEN LLM genera respuesta → formato JSON válido con los 3 campos obligatorios
- WHEN `pragmatic_actions` generadas → entre 1 y 3, nunca 0 ni más de 3
- WHEN N11 completa → `DraftReport` persistido en `audit_results` antes de entregar a N12
- WHEN mismo `layer3_run_id` enviado dos veces → retornar resultado existente (idempotencia)

---

## Edge Cases

- LLM timeout → `node_status: "failed"`, N12 no se ejecuta, error reportado al cliente
- `brand_identity.retrieved: false` → N11 opera sin restricciones de marca, agrega nota en `executive_summary`
- `historical_context` vacío → N11 no asume causas históricas, analiza solo datos actuales
- `forensic_report.anomalies` vacío → `executive_summary` refleja salud positiva del período
- LLM genera JSON inválido → reintentar 1 vez con temperatura reducida, luego `node_status: "failed"`

---

## Correctness Properties (PBT)

| ID | Propiedad |
|----|-----------|
| P1 | `DraftReport.temporalidad` == `EnrichedAuditPayload.temporalidad` siempre |
| P2 | `len(pragmatic_actions)` siempre entre 1 y 3 inclusive |
| P3 | `draft_status` siempre `"draft"` — nunca `"final"` en N11 |
| P4 | `brand_identity.retrieved: true` → ninguna `pragmatic_action` contradice `brand_identity.content` |
| P5 | `forensic_report` referenciado es de S4, nunca de N07 |
| P6 | Mismo `layer3_run_id` → exactamente 1 registro en `audit_results` |
| P7 | LLM response inválida → reintento antes de `node_status: "failed"` |

---

## Archivos relacionados de este nodo
- `n10_context_builder.md` — `EnrichedAuditPayload` (input)
- `n12_phrase_expander.md` — consumidor del `DraftReport`
- `s4_auditoria_ia.md` — origen del `forensic_report`
- `n05_ceo_orchestrator.md` — origen de `audit_insights`
- `_glossary.md` — contratos `DraftReport`, `PragmaticAction`
