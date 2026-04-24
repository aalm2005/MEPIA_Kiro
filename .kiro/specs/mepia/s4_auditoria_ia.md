# S4 — Nodo de Auditoría (IA)

**Capa:** Sequential | **Anterior:** S3 Motor de Cálculo | **Siguiente:** Layer 2 Parallel
**Responsabilidad:** Interpretar números crudos ponderando contexto. Genera insights CEO-framed.

## Separación de responsabilidades

```
S3 (Python)  →  QUÉ pasó (número puro)
S4 (IA)      →  POR QUÉ pasó + QUÉ hacer (interpretación contextual)
```

## Gestión de Arquetipos

El arquetipo se pasa como parámetro en el request al endpoint de auditoría. No hay sesión ni estado en servidor — cada llamada es stateless. S4 inyecta los datos de S3 en la plantilla del arquetipo recibido.

### Diccionario de Prompt Templates

Cada template tiene instrucciones base que **prohíben resúmenes genéricos** y obligan a frases directas y pragmáticas.

| Arquetipo          | Enfoque del prompt                                                        |
|--------------------|---------------------------------------------------------------------------|
| Operative Genius   | Traduce métricas en alertas sobre cuellos de botella y fugas de capital en procesos |
| Product Purist     | Traduce control de costos en impacto directo a la calidad del producto/experiencia |
| Growth Hacker      | Traduce métricas en oportunidades de escala, recompra y crecimiento       |

### Ejemplo de instrucción base (Operative Genius)
```
Eres un auditor operativo. Dado un resultado numérico y su contexto:
- Identifica el cuello de botella específico
- Cuantifica la fuga de capital en MXN
- Propón una acción correctiva con frecuencia definida
- PROHIBIDO: frases genéricas como "considera revisar" o "podría mejorar"
```

## Input

```
calc_results: CalcResult[]       // array de resultados de S3
context: daily_context.tags      // JSONB del día
archetype: "Operative Genius" | "Product Purist" | "Growth Hacker"
```

El campo `archetype` es obligatorio en el request body. Si no se envía → default `"Operative Genius"`.
No se persiste en sesión — el cliente es responsable de enviarlo en cada request.

### Endpoint

`POST /audit/run`

**Request body — `AuditRunPayload`:**

```python
class AuditRunPayload(BaseModel):
    business_id: UUID
    date: date
    archetype: Literal[
        "Operative Genius", "Product Purist", "Growth Hacker"
    ] = "Operative Genius"
```

S4 recupera internamente los `CalcResult[]` de S3 y los `daily_context.tags` usando `business_id + date`. El cliente no necesita enviarlos.

**Response 200:**
```json
{
  "business_id": "uuid-v4",
  "date": "2024-01-15",
  "archetype": "Operative Genius",
  "insights": [
    {
      "module": "conciliacion_caja",
      "raw_result": "variance: -320 MXN",
      "copilot_phrase": "...",
      "alert_level": "critical",
      "recommended_action": "Revisión de caja inmediata",
      "context_weight": "normal"
    }
  ]
}
```

**Códigos de error:**

| HTTP | Condición                                              |
|------|--------------------------------------------------------|
| 404  | `business_id` no existe                                |
| 422  | `archetype` con valor inválido                         |
| 409  | No hay métricas `active` para `business_id + date` — S3 no ha corrido |

## Output — `AuditInsight`

```
module: string
raw_result: string               // número crudo de S3
copilot_phrase: string           // frase CEO-framed, específica y accionable
archetype: CEO Archetype
alert_level: "info" | "warning" | "critical"
recommended_action: string       // acción específica, nunca null en warning/critical
context_weight: "reducido" | "normal" | "amplificado"
```

## Lógica de ponderación

| Métrica baja + Contexto           | alert_level | context_weight |
|-----------------------------------|-------------|----------------|
| Ventas ↓ + `lluvia`               | warning     | reducido       |
| Ventas ↓ + `falla_maquina`        | warning     | reducido       |
| Ventas ↓ + sin tag relevante      | critical    | normal         |
| Margen ↓ + `promocion`            | info        | reducido       |
| Margen ↓ + sin tag relevante      | critical    | amplificado    |
| Conciliación negativa > 1%        | critical    | normal (siempre, sin reducción por contexto) |

## Ejemplo de salida (Operative Genius)

```
S3 detecta:  margen_utilidad.delta = -10%, conciliacion_caja.variance = -$320
Contexto:    equipo = "falla_maquina", otros = "Espresso fuera 3h"

copilot_phrase: "Tu margen bajó 10% por inactividad de la máquina de espresso
                 (3h = costo de oportunidad estimado $480). Adicionalmente,
                 hay una varianza de -$320 en caja que requiere revisión
                 independiente del contexto. Acción: mantenimiento preventivo
                 cada 90 días + auditoría de caja hoy."
alert_level: "critical"
recommended_action: "Mantenimiento preventivo + revisión de caja inmediata"
```

## Acceptance Criteria

- WHEN `archetype` ausente en request → usar `"Operative Genius"` como default
- WHEN `conciliacion_caja` crítica → `alert_level: "critical"` sin importar contexto
- WHEN múltiples métricas críticas → consolidar en una sola frase coherente, no lista
- WHEN `recommended_action` en warning/critical → debe incluir frecuencia o plazo específico
- WHEN tags vacíos → tratar como contexto "Normal", no reducir peso de alertas
- WHEN no hay métricas `active` para `business_id + date` → HTTP 409, no ejecutar S4
