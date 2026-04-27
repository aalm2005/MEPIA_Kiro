# S3 — Motor de Cálculo (Python)

**Capa:** Sequential | **Anterior:** S2 Gatekeeper | **Siguiente:** S4 Forensic CFO
**Archivo de implementación:** `agents/calc_engine.py`
**Responsabilidad:** Cálculos financieros puros. Sin IA, sin interpretación, solo números.

## Reglas de Oro

1. Cero cálculos en LLM — agentes solo leen resultados de estas funciones
2. Normalización de unidades obligatoria antes de operar
3. División por cero o dato faltante → `status: "incomplete_data"`, nunca romper el proceso
4. Solo opera sobre métricas con `status: "active"` del Gatekeeper

## Distinción Fijo vs Variable — Flujo API-First

`expense_behavior` (ENUM: `FIXED` | `VARIABLE` | `CAPEX`) en `transactions`.

Flujo de confirmación vía API (ver contrato completo en `n03_human_input_endpoints.md`):
```
1. S1/N02 extrae gasto → expense_behavior = null en transactions
2. Cliente consulta GET /transactions/pending-review para ver pendientes
3. Sistema sugiere expense_behavior por supplier_name/concept (nunca persiste automáticamente)
4. Cliente envía PATCH /transactions/{id}/expense-behavior con valor confirmado
5. Solo tras confirmación → gasto disponible para S3
```
S3 nunca asume `expense_behavior` — solo usa gastos con valor confirmado explícitamente.

## Normalización de Unidades

| Unidad origen | Unidad base | Factor |
|---------------|-------------|--------|
| kg            | g           | × 1000 |
| L             | ml          | × 1000 |
| unidad        | unidad      | × 1    |

Unidades incompatibles → `status: "unit_mismatch"`, no calcular.

## Formato de respuesta — `CalcResult`

```json
{
  "metric": "merma_leche",
  "value": 12.5,
  "unit": "litros",
  "status": "ok | warning | critical | incomplete_data | unit_mismatch",
  "context": "Se compraron 100L, se debieron usar 87.5L según recetas."
}
```

## Funciones

### `calc_contribution_margin(product_id)`
```
MC = precio_venta - sum(ingrediente_qty × precio_unitario)
```
Edge: sin receta → `incomplete_data`

### `calc_daily_break_even(business_id)`
```
PE = (sum(FIXED expenses del mes) / 30) / MC_promedio
```
Usa solo `transactions` con `expense_behavior = "FIXED"` confirmado vía API.
Edge: MC_promedio = 0 → `incomplete_data`

### `calc_waste_analysis(ingredient_id, start_date, end_date)`
```
merma = insumos_comprados - (ventas × cantidad_en_receta)
```
Normalizar unidades antes de restar. Edge: unidades incompatibles → `unit_mismatch`

### `calc_burn_rate(business_id)`
```
BR = sum(FIXED + VARIABLE expenses del mes) / 30
```
Edge: sin gastos confirmados → `incomplete_data`

### `check_price_inflation(ingredient_id)`
```
delta = ((precio_ultima_factura - precio_promedio_anteriores) / precio_promedio_anteriores) × 100
```
Edge: solo 1 factura → `incomplete_data`

### `calc_cash_reconciliation(business_id, date)` ← NUEVA
```
expected_cash = initial_float + pos_cash_sales - refunds - cash_payouts
variance = actual_cash_counted - expected_cash
```
- Input: `pos_inputs` + `cash_count` manual del día
- Output: `{ metric: "conciliacion_caja", value: variance, unit: "MXN", status, context }`
- WHEN variance negativa > 1% de ventas en efectivo → `status: "critical"`, alerta a S4

## Umbrales de status

| Métrica              | warning       | critical                        |
|----------------------|---------------|---------------------------------|
| Merma                | > 5%          | > 15%                           |
| Inflación precio     | delta 5–15%   | delta > 15%                     |
| Conciliación caja    | variance < 0  | variance < -1% de ventas        |
| Margen contribución  | MC < 20%      | MC < 10%                        |

## Extensibilidad

Nueva métrica: crear `calc_nueva_metrica()` → retorna `CalcResult`. No modificar funciones existentes. Registrar prerrequisitos en S2.
