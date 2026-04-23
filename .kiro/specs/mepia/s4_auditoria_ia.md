# S4 — Nodo de Auditoría (IA)

**Capa:** Sequential | **Anterior:** S3 Motor de Cálculo | **Siguiente:** Layer 2 Parallel
**Responsabilidad:** Interpretar números crudos ponderando el contexto del día. Genera insights CEO-framed.

## Separación de responsabilidades

```
S3 (Python)  →  QUÉ pasó (número puro)
S4 (IA)      →  POR QUÉ pasó + QUÉ hacer (interpretación contextual)
```

## Lógica de ponderación

La IA compara cada métrica contra los tags de contexto del día (`daily_context.tags`) y ajusta el peso de la alerta:

| Métrica baja + Contexto          | Acción IA              |
|----------------------------------|------------------------|
| Ventas ↓ + tag `lluvia`          | Restar peso a alerta   |
| Ventas ↓ + tag `falla_maquina`   | Restar peso + cuantificar costo de oportunidad |
| Ventas ↓ + sin tag relevante     | Disparar "Acción Crítica" |
| Margen ↓ + tag `promocion`       | Restar peso, esperado  |
| Margen ↓ + sin tag relevante     | Disparar "Acción Crítica" |

## Input

```
calc_result: CalcResult          // números de S3
context: daily_context.tags      // JSONB del día
archetype: CEO Archetype         // del CEO Orchestrator Layer
```

## Output

`AuditInsight` (extiende `AgentResult`):
```
module: string
raw_result: string               // número crudo de S3
copilot_phrase: string           // frase CEO-framed
archetype: CEO Archetype
alert_level: "info" | "warning" | "critical"
recommended_action: string | null
context_weight: "reducido" | "normal" | "amplificado"
```

## Ejemplo de salida (Cafetería)

```
Python detecta:  margen_utilidad.delta = -10%
Contexto:        tags.equipo = "falla_maquina", otros = "Espresso fuera 3h"

IA genera:
  copilot_phrase: "Tu margen bajó un 10% debido al tiempo de inactividad
                   de la máquina de espresso reportada. El costo de
                   oportunidad fue de $X. Recomiendo mantenimiento
                   correctivo cada 3 meses para evitar recurrencia."
  alert_level: "warning"          // reducido por contexto
  context_weight: "reducido"
  recommended_action: "Agendar mantenimiento correctivo"
```

## Acceptance Criteria

- WHEN `delta` negativo + tag contextual relevante → `alert_level: "warning"`, `context_weight: "reducido"`
- WHEN `delta` negativo + sin tag relevante → `alert_level: "critical"`, `context_weight: "normal"`
- WHEN `delta` positivo → `alert_level: "info"`, frase de refuerzo positivo
- WHEN `recommended_action` generada → debe ser accionable y específica (no genérica)
- WHEN archetype = "Operative Genius" → frase enfocada en eficiencia y procesos
- WHEN archetype = "Growth Hacker" → frase enfocada en métricas de escala y recompra

## Edge Cases

- Múltiples tags contradictorios (ej. `lluvia` + `promocion`) → IA pondera ambos, explica en frase
- Métrica sin delta (primer período) → `alert_level: "info"`, frase de baseline
- Tags vacíos (`null`) → tratar como contexto "Normal"
