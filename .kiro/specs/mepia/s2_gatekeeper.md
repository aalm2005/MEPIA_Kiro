# S2 — Stand-by / Gatekeeper

**Capa:** Sequential | **Anterior:** S1 Ingesta | **Siguiente:** S3 Motor de Cálculo
**Archivos relacionados:** `db_schema.md`, tabla `metric_status`

## Responsabilidad

Valida que cada métrica tenga su set de datos completo antes de pasar a S3. Nunca asume datos — solo activa métricas con evidencia confirmada.

## Triggers

| Trigger         | Cuándo se dispara                                                        |
|-----------------|--------------------------------------------------------------------------|
| Event-driven    | INSERT o UPDATE en `transactions` o `pos_inputs`                         |
| Schedule (CRON) | Cierre de día — evalúa métricas de resumen                               |
| API manual      | `PATCH /transactions/{id}/expense-behavior` → re-evalúa `daily_break_even` |
| API manual      | `POST /cash-counts` → re-evalúa `cash_reconciliation`                    |

Todos los triggers de intervención humana llegan vía endpoints definidos en `n03_human_input_endpoints.md`. S2 no depende de UI.

## Catálogo de métricas (alineado 1:1 con S3)

| Métrica                  | Datos requeridos                                                    |
|--------------------------|---------------------------------------------------------------------|
| `daily_break_even`       | `transactions` con `expense_behavior` confirmado al día de corte   |
| `cash_reconciliation`    | Ventas POS (`pos_inputs`) + conteo manual de cajón (`cash_count`)  |
| `operative_cost_margin`  | `transactions` categorizadas (insumos vs operativos)               |
| `health_score`           | Cálculo exitoso de las 3 métricas anteriores                        |
| `inventory_variance`     | BOM cargado (`recipes`) + recuento físico + ventas POS             |

## Flujo de validación

```
Para cada métrica en el catálogo:
  1. Consultar datos en transactions + pos_inputs + recipes + cash_count
  2. Verificar que needs_human_review = false en todos los documentos del día
  3. Evaluar si el set requerido está completo
  4. Escribir en metric_status: { metric_name, business_id, date, status, missing_fields[] }
  5. Retornar active_metrics[] a S3
```

## Output — `GatekeeperResult`

```
business_id: UUID
date: YYYY-MM-DD
active_metrics: string[]
dormant_metrics: [{ metric: string, missing: string[] }]
blocked_metrics: [{ metric: string, reason: "needs_human_review" }]
```

## Acceptance Criteria

- WHEN documento con `needs_human_review: true` → métricas dependientes en `blocked`, no `dormant`
- WHEN ventas POS sin conteo de cajón → `cash_reconciliation` en `dormant`, `missing: ["cash_count"]`
- WHEN `expense_behavior` no confirmado en algún gasto → `daily_break_even` en `dormant`
- WHEN `health_score` requerido pero alguna métrica base en `dormant` → `health_score` en `dormant`
- WHEN todas las métricas en `dormant` o `blocked` → S3 no se ejecuta, notificar al usuario
- WHEN `metric_status` ya existe para `business_id + date` → sobrescribir

## Edge Cases

- Receta desactualizada (> 30 días sin editar) → `active` con warning en `missing_fields`
- Datos de solo turno matutino → `dormant` hasta cierre o confirmación manual del usuario
