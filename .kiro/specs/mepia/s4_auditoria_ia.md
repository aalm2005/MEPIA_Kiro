# S4 — Forensic CFO (Nodo de Auditoría IA)

**Capa:** Sequential | **Anterior:** S3 Motor de Cálculo | **Siguiente:** N05 CEO Orchestrator
**Responsabilidad:** Diagnóstico forense de anomalías financieras. Sin recomendaciones. Sin arquetipos.

## Decisión de LLM

| Campo | Valor |
|-------|-------|
| **Modelo** | `gpt-4o` |
| **Proveedor** | OpenAI |
| **Temperatura** | `0` — determinismo máximo para diagnóstico forense |
| **Justificación** | Razonamiento lógico-matemático estricto y salida estructurada (`ForensicReport`). Requiere precisión en cuantificación de anomalías y clasificación de severidad sin ambigüedad. |
| **Variable de entorno requerida** | `OPENAI_API_KEY` |

## Separación de responsabilidades

```
S3 (Python)  →  QUÉ pasó (número puro)
S4 (IA)      →  DÓNDE está la fuga + CUÁL es la evidencia (diagnóstico forense)
N05 (CEO)    →  POR QUÉ importa + QUÉ hacer (síntesis estratégica con arquetipo)
```

S4 nunca reduce la severidad de una anomalía por contexto externo.
Si hay una fuga del 10%, reporta `risk_level: "high"` y adjunta el tag de `daily_context`
bajo `observed_causality`. Será N05 quien decida cómo redactar la recomendación.

---

## System Prompt Base (Forensic CFO)

```
Eres el Auditor Forense Financiero (S4) del sistema MEPIA.
Tu único objetivo es el diagnóstico clínico y la cuantificación de desviaciones operativas.
Operas con precisión quirúrgica.

REGLAS ESTRICTAS:
1. PROHIBIDO sugerir soluciones, mejoras, o estrategias de mitigación.
   Tu trabajo es el diagnóstico, no la consultoría.
2. PROHIBIDO usar lenguaje empático, de "CEO", motivacional o de negocios.
   Mantén un tono estrictamente analítico, contable y forense.
3. PROHIBIDO especular sobre las causas si no están respaldadas explícitamente
   en los datos (evidence_sources).
4. LIMITA tu salida a la identificación de la anomalía, el cálculo de su impacto
   matemático y la categorización del riesgo.
5. PROHIBIDO consolidar múltiples anomalías en una sola frase — cada AnomalyItem
   es independiente y debe documentarse por separado.
6. PROHIBIDO omitir el campo quantified_impact — si no puede calcularse con precisión,
   usa un rango estimado con la fuente de datos usada.
```

---

## Las 3 preguntas forenses (criterios de completitud del output)

El `ForensicReport` de S4 debe responder obligatoriamente estas tres preguntas.
Si no puede responder alguna por falta de datos, el campo correspondiente es `null`
con una nota en `evidence_sources`.

| # | Pregunta | Campo en output |
|---|----------|-----------------|
| 1 | ¿Dónde se está fugando el margen exactamente? | `anomalies` con `type: "margin_leak"` |
| 2 | ¿Qué inconsistencias existen entre flujo de caja y operación? | `anomalies` con `type: "source_discrepancy"` |
| 3 | ¿Cuál es el límite matemático de producción detectado en la data? | `anomalies` con `type: "operational_ceiling"` |

---

## Input

```
calc_results: CalcResult[]         // array de resultados de S3
daily_context: DailyContextTags    // tags del día — solo para observed_causality, no para ponderar
business_id: UUID
date: date
```

S4 recupera internamente `CalcResult[]` y `daily_context.tags` usando `business_id + date`.
El cliente no necesita enviarlos.

### Endpoint

`POST /audit/run`

**Request body — `AuditRunPayload`:**

```python
class AuditRunPayload(BaseModel):
    business_id: UUID
    date: date
```

> Nota: `archetype` eliminado del request de S4. El arquetipo es responsabilidad de N05.

**Response 200:** `ForensicReport` (ver contrato abajo)

**Códigos de error:**

| HTTP | Condición |
|------|-----------|
| 404  | `business_id` no existe |
| 409  | No hay métricas `active` para `business_id + date` — S3 no ha corrido |

---

## Output — `ForensicReport`

Contrato de salida estricto de S4. No contiene frases CEO-framed ni recomendaciones.

```
business_id: UUID
date: date
risk_level: "low" | "medium" | "high"   // nivel global del reporte
anomalies: AnomalyItem[]                 // lista de anomalías detectadas
evidence_sources: string[]               // fuentes comparadas: ["POS", "facturas", "cash_count"]
observed_causality: DailyContextTags | null  // tags del día adjuntos sin interpretación
generated_at: datetime
```

### `AnomalyItem`

```
anomaly_id: UUID
type: "margin_leak" | "source_discrepancy" | "operational_ceiling" | "cost_spike" | "other"
description: string          // descripción técnica precisa, sin lenguaje CEO
severity: "low" | "medium" | "high"
quantified_impact: string    // ej. "-320 MXN", "-10% margen", "techo: 180 unidades/día"
data_points: string[]        // evidencia numérica específica de S3 que sustenta la anomalía
metric_origin: string        // nombre de la CalcResult que originó la anomalía
```

### Reglas de `risk_level` global

| Condición | `risk_level` |
|-----------|-------------|
| ≥ 1 anomalía con `severity: "high"` | `"high"` |
| Solo anomalías `"medium"` | `"medium"` |
| Solo anomalías `"low"` o sin anomalías | `"low"` |

### Regla de `observed_causality`

S4 adjunta `daily_context.tags` tal cual en `observed_causality` — sin interpretación.
N05 decide si esa causalidad justifica suavizar la recomendación al dueño.
S4 **nunca** modifica `severity` basándose en el contexto.

---

## Ejemplo de output (Forensic CFO)

```
S3 detecta:  margen_utilidad.delta = -10%, conciliacion_caja.variance = -320 MXN
Contexto:    equipo = "falla_maquina", otros = "Espresso fuera 3h"

ForensicReport:
  risk_level: "high"
  anomalies: [
    {
      type: "margin_leak",
      severity: "high",
      description: "Margen de utilidad cayó 10 puntos porcentuales vs período anterior",
      quantified_impact: "-10% margen (~$1,200 MXN estimado)",
      data_points: ["margen_utilidad.value: 8%", "margen_utilidad.delta: -10%"],
      metric_origin: "margen_utilidad"
    },
    {
      type: "source_discrepancy",
      severity: "high",
      description: "Varianza negativa entre ventas POS y efectivo contado en cajón",
      quantified_impact: "-320 MXN",
      data_points: ["conciliacion_caja.variance: -320", "pos_inputs.cash_sales: 4820"],
      metric_origin: "conciliacion_caja"
    }
  ]
  evidence_sources: ["POS", "cash_count"]
  observed_causality: { equipo: "falla_maquina", otros: "Espresso fuera 3h" }
```

---

## Acceptance Criteria

- WHEN S3 no ha corrido para `business_id + date` → HTTP 409, no ejecutar S4
- WHEN hay anomalía de tipo `source_discrepancy` → `severity` siempre `"high"`, sin excepción
- WHEN `daily_context` existe → adjuntar en `observed_causality` sin modificar ningún `severity`
- WHEN `daily_context` no existe → `observed_causality: null`, severidades sin cambio
- WHEN múltiples anomalías → cada una en su propio `AnomalyItem`, no consolidadas en texto
- WHEN no hay anomalías detectadas → `anomalies: []`, `risk_level: "low"`
- WHEN `quantified_impact` no puede calcularse → string descriptivo, nunca `null`

---

## Correctness Properties (PBT)

| ID | Propiedad |
|----|-----------|
| P1 | `observed_causality` nunca modifica `severity` de ningún `AnomalyItem` |
| P2 | `risk_level: "high"` ↔ existe al menos 1 `AnomalyItem` con `severity: "high"` |
| P3 | `source_discrepancy` siempre tiene `severity: "high"` independientemente del contexto |
| P4 | `ForensicReport` sin `archetype` — campo inexistente en el output |
| P5 | `evidence_sources` contiene solo fuentes que realmente se compararon en esa ejecución |
