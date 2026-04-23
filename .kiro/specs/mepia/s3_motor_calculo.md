# S3 — Motor de Cálculo (Python)

**Capa:** Sequential | **Anterior:** S2 Gatekeeper | **Siguiente:** S4 Auditoría IA
**Archivo de implementación:** `agents/calc_engine.py`
**Responsabilidad:** Cálculos financieros puros. Sin IA, sin interpretación, solo números.

## Reglas de Oro

1. Cero cálculos en LLM — los agentes solo leen resultados de estas funciones
2. Normalización de unidades obligatoria antes de operar (ver sección abajo)
3. División por cero o dato faltante → retornar `status: "incomplete_data"`, nunca romper el proceso

## Normalización de Unidades (CRÍTICO)

Toda operación entre cantidades debe pasar por el validador de unidades antes de ejecutarse.

| Unidad origen | Unidad base | Factor |
|---------------|-------------|--------|
| kg            | g           | × 1000 |
| L             | ml          | × 1000 |
| unidad        | unidad      | × 1    |

Regla: si receta usa `g` y factura usa `kg`, convertir factura a `g` antes de restar. Nunca operar entre unidades distintas — retornar `status: "unit_mismatch"` si no hay conversión definida.

## Formato de respuesta estándar (CalcResult)

Toda función retorna este objeto:
```json
{
  "metric": "merma_leche",
  "value": 12.5,
  "unit": "litros",
  "status": "ok | critical | warning | incomplete_data | unit_mismatch",
  "context": "Se compraron 100L, se debieron usar 87.5L según recetas."
}
```

## Funciones del módulo

### `calc_contribution_margin(product_id)`
Margen de contribución por producto.

```
MC = precio_venta - sum(ingrediente_qty * precio_unitario para cada ingrediente en receta)
```

- Input: `product_id` → busca en `recipes` + precios en `transactions`
- Output: `{ metric: "margen_contribucion", value: MC, unit: "MXN", status, context }`
- Edge: producto sin receta → `incomplete_data`

### `calc_daily_break_even(business_id)`
Punto de equilibrio diario en unidades vendidas.

```
PE = (gastos_fijos_mensuales / 30) / MC_promedio
```

- Input: `business_id` → gastos fijos de `transactions` (category: "nomina" + "proveedor" fijos) + MC promedio de todos los productos
- Output: `{ metric: "punto_equilibrio_diario", value: PE, unit: "unidades", status, context }`
- Edge: MC promedio = 0 → `incomplete_data` (división por cero)

### `calc_waste_analysis(ingredient_id, start_date, end_date)`
Merma de un insumo en un período.

```
merma = insumos_comprados - (ventas_por_producto × cantidad_en_receta)
```

- Input: `ingredient_id`, rango de fechas → `transactions` (compras) + `recipes` + ventas del período
- Normalización: unificar unidades de compra y receta a unidad base antes de restar
- Output: `{ metric: "merma_{ingrediente}", value: merma, unit: unidad_base, status, context }`
- Edge: unidades incompatibles → `unit_mismatch`; sin ventas del período → `incomplete_data`

### `calc_burn_rate(business_id)`
Costo operativo diario promedio.

```
BR = sum(gastos_fijos_mensuales) / 30
```

- Input: `business_id` → `transactions` con `category` in ["nomina", "proveedor", "impuesto"] del mes
- Output: `{ metric: "burn_rate_diario", value: BR, unit: "MXN/día", status, context }`
- Edge: sin gastos registrados → `incomplete_data`

### `check_price_inflation(ingredient_id)`
Detecta inflación de precio de un insumo.

```
delta = ((precio_ultima_factura - precio_promedio_anteriores) / precio_promedio_anteriores) * 100
```

- Input: `ingredient_id` → últimas N facturas en `transactions` (category: "proveedor")
- Output: `{ metric: "inflacion_{ingrediente}", value: delta, unit: "%", status, context }`
- Status: `critical` si delta > 15%, `warning` si 5–15%, `ok` si < 5%
- Edge: solo 1 factura disponible → `incomplete_data` (sin histórico para comparar)

## Acceptance Criteria

- WHEN unidades distintas en receta vs factura → normalizar a unidad base antes de operar
- WHEN normalización imposible (unidades incompatibles) → `status: "unit_mismatch"`, no calcular
- WHEN división por cero → `status: "incomplete_data"`, `value: null`
- WHEN dato requerido ausente en DB → `status: "incomplete_data"`, `context` describe qué falta
- WHEN cálculo exitoso → `value` con 2 decimales, `status` según umbrales definidos
- Cada función es independiente — el fallo de una no afecta las demás

## Umbrales de status

| Métrica              | warning       | critical      |
|----------------------|---------------|---------------|
| Merma                | > 5%          | > 15%         |
| Inflación precio     | delta 5–15%   | delta > 15%   |
| Burn rate vs ventas  | cubre < 80%   | cubre < 60%   |
| Margen contribución  | MC < 20%      | MC < 10%      |

## Extensibilidad

Para agregar una nueva métrica: crear función `calc_nueva_metrica()` que retorne `CalcResult`. No modificar funciones existentes. El Gatekeeper (S2) debe registrar los datos requeridos para la nueva métrica en `metric_status`.
