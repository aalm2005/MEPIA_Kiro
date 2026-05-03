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

## Funciones auxiliares puras

### `normalize_units(value, from_unit, to_unit, conversions) -> Decimal | None`
Convierte entre unidades usando la lista `conversions` (ya cargada desde DB).
- `from_unit == to_unit` → retorna value sin cambio.
- Sin conversión disponible → retorna `None` (el caller emite `unit_mismatch`).

### `days_in_month(date_str) -> int`
Retorna días reales del mes (28/29/30/31) para una fecha YYYY-MM-DD.
Usa `calendar.monthrange` — respeta años bisiestos. NUNCA retorna 30 fijo.

## Funciones

### `calc_contribution_margin(product_id, db)`
```
MC = precio_venta - sum(ingrediente_qty × precio_unitario)
```
- `precio_unitario`: última factura del ingrediente en `transactions`.
- Edge: sin receta → `incomplete_data`; ingrediente sin factura → `incomplete_data`.

### `calc_daily_break_even(business_id, date)`
```
PE_unidades = (sum(FIXED expenses del mes) / days_in_month(date)) / MC_promedio
```
Usa solo `transactions` con `expense_behavior = "FIXED"` confirmado vía API.
Divisor: `days_in_month(date)` — NUNCA 30 fijo.
Edge: MC_promedio = 0 → `incomplete_data`; sin gastos FIXED → `incomplete_data`

### `calc_waste_analysis(ingredient_id, start_date, end_date, business_id, db)`
```
merma_pct = (comprado_base - consumo_teorico_base) / comprado_base × 100
```
- Normalizar unidades con `unit_conversions` antes de restar.
- `consumo_teorico` = sum(ventas_producto × qty_ingrediente_en_receta) desde `pos_inputs`.
- Edge: unidades incompatibles → `unit_mismatch`; sin compras → `incomplete_data`.

### `calc_burn_rate(business_id, date)`
```
BR = sum(FIXED + VARIABLE expenses del mes) / days_in_month(date)
```
Divisor: `days_in_month(date)` — NUNCA 30 fijo.
Edge: sin gastos confirmados → `incomplete_data`. Sin umbrales (siempre "ok" si hay datos).

### `check_price_inflation(ingredient_id, business_id, db)`
```
delta_pct = ((precio_ultima_factura - precio_promedio_anteriores) / precio_promedio_anteriores) × 100
```
- Facturas ordenadas por `transaction_date DESC`; la primera es la más reciente.
- Edge: solo 1 factura → `incomplete_data`; precio_promedio = 0 → `incomplete_data`.

### `calc_cash_reconciliation(business_id, date, db)`
```
expected_cash = initial_float + pos_cash_sales - refunds - cash_payouts
variance      = actual_cash_counted - expected_cash
variance_pct  = variance / pos_cash_sales × 100  (si pos_cash_sales > 0)
```
- Input: `pos_inputs` (cash_sales, refunds) + `cash_counts` (initial_float, actual_counted, cash_payouts).
- `value`: variance en MXN.
- Si `pos_cash_sales = 0` → usar variance absoluta para determinar status.
- Edge: sin pos_inputs o sin cash_counts → `incomplete_data`.

## Umbrales de status

| Métrica              | warning            | critical                        |
|----------------------|--------------------|--------------------------------------|
| Merma                | merma_pct > 5%     | merma_pct > 15%                      |
| Inflación precio     | delta_abs 5–15%    | delta_abs > 15%                      |
| Conciliación caja    | variance < 0       | variance_pct < -1% de ventas         |
| Margen contribución  | MC_pct < 20%       | MC_pct < 10%                         |
| Burn rate            | —                  | — (siempre "ok" si hay datos)        |
| Punto de equilibrio  | —                  | — (siempre "ok" si hay datos)        |

## Extensibilidad

Nueva métrica: crear `calc_nueva_metrica()` → retorna `CalcResult`. No modificar funciones existentes. Registrar prerrequisitos en S2.
