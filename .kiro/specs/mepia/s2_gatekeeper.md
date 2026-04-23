# S2 — Stand-by / Gatekeeper

**Capa:** Sequential | **Anterior:** S1 Ingesta | **Siguiente:** S3 Motor de Cálculo
**Archivos relacionados:** `db_schema.md`, tabla `metric_status`

## Responsabilidad

Script de validación Python que corre antes de cualquier cálculo. Determina qué métricas tienen suficientes datos para calcularse (`active`) y cuáles deben esperar (`dormant`).

## Lógica de estados

| Estado    | Significado                                      |
|-----------|--------------------------------------------------|
| `dormant` | Faltan datos requeridos. Métrica no se calcula.  |
| `active`  | Set de datos completo. Métrica lista para S3.    |

## Requisitos por métrica

| Métrica              | Datos requeridos                          |
|----------------------|-------------------------------------------|
| Margen de utilidad   | Ventas + Costos operativos                |
| Merma                | Ventas + Compras de insumos + Receta (BOM)|
| Conciliación de caja | Ventas POS + Depósitos reportados         |
| Costo por producto   | Receta (BOM) + Precios de insumos         |
| Cumplimiento PLD     | Transacciones en efectivo > umbral        |

## Flujo de validación

```
Para cada métrica en el catálogo:
  1. Consultar datos disponibles en transactions + documents + recipes
  2. Evaluar si el set requerido está completo
  3. Escribir resultado en metric_status:
     { metric_name, business_id, date, status, missing_fields[] }
  4. Retornar solo métricas con status = "active" al S3
```

## Output

`GatekeeperResult`:
```
business_id: UUID
date: YYYY-MM-DD
active_metrics: string[]       → pasan a S3
dormant_metrics: [
  { metric: string, missing: string[] }
]
```

## Acceptance Criteria

- WHEN hay ventas pero no facturas de insumos → métrica "Merma" en `dormant`, `missing: ["compras_insumos"]`
- WHEN hay ventas + costos pero no receta → métrica "Costo por producto" en `dormant`, `missing: ["recipe"]`
- WHEN set completo → métrica en `active`, pasa a S3
- WHEN todas las métricas en `dormant` → S3 no se ejecuta, notificar al usuario qué datos faltan
- WHEN `metric_status` ya existe para `business_id + date` → sobrescribir, no duplicar

## Edge Cases

- Datos parciales del día (ej. solo turno matutino) → `dormant` hasta cierre de día o confirmación manual
- Receta desactualizada (> 30 días sin editar) → `active` pero con warning en `missing_fields`
