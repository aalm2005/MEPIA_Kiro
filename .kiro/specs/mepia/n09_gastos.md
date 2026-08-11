# N09 — Agente de Auditoría Operativa y Financiera

**Capa:** Parallel (Layer 2) | **Anterior:** N06 Orquestador ADK | **Siguiente:** Consolidación en N06 → N11 Consultor
**Archivo de implementación:** `agents/business_health.py`
**Patrón:** Nodo paralelo — retorna `NodeResult` al orquestador N06
**Timeout asignado por N06:** configurable vía `node_timeouts.n09_gastos` (default 20s)

## Decisión de LLM

| Campo | Valor |
|-------|-------|
| **Modelo** | `gpt-4o-mini` |
| **Proveedor** | OpenAI |
| **Temperatura** | `0.2` |
| **Justificación** | Nodo de soporte no crítico. Genera únicamente `copilot_phrase` — una frase de apoyo sobre el `FinancialAuditResult` ya calculado por Python. Si el LLM falla, el nodo sigue siendo `"success"` con `copilot_phrase: null`. Prioridad: velocidad y bajo costo dentro del timeout de 20s. |
| **Variable de entorno requerida** | `OPENAI_API_KEY` |
| **Fallback** | Si el LLM falla o hace timeout → `copilot_phrase: null`, `status: "success"`. No hay fallback a otro modelo — el `raw_result` es suficiente para N11. |

---

## Responsabilidad

Actuar como el Contralor/Director Financiero del restaurante. Evalúa rentabilidad y eficiencia
cruzando ventas diarias, gastos operativos (fijos y variables) y el ciclo de vida del negocio
para detectar fugas de capital o bajo rendimiento.

N09 **no** busca descuadres de caja — eso es N07. Su dominio es la rentabilidad estructural.

---

## Diferenciación de nodos paralelos

| Nodo | Dominio                             |
|------|-------------------------------------|
| N07  | Descuadre de caja (efectivo)        |
| N08  | Cumplimiento PLD                    |
| N09  | Rentabilidad y eficiencia operativa |

---

## Input

Recibe `Layer2RunPayload` desde N06. Usa directamente:

```python
business_id: UUID
date: date
sequential_context.calc_results    # CalcResult[] de S3
archetype                          # para generar copilot_phrase
```

> **Nota:** `sequential_context.context_tags` (daily_context) fue retirado — ya no se recibe ni se usa.

Además consulta Supabase directamente para las heurísticas:
- `businesses.opening_date` — para ciclo de vida
- `business_fixed_costs` — para costo fijo diario
- `transactions` del día — gastos VARIABLE y CAPEX **confirmados** (`needs_human_review = false`)
- `documents` del día — para detectar facturas pendientes de revisión
- `pos_inputs` del día y los 7 días calendario **anteriores** a `date` con `total_sales > 0`

---

## Heurísticas (Python/SQL — sin LLM)

Las 3 heurísticas corren en paralelo interno antes de invocar al LLM.
Producen el `raw_result` que el LLM interpreta para generar `copilot_phrase`.

### A) Break-Even + Curva de Vida del Negocio

```
1. business_age_months = months_between(opening_date, date)

2. days_in_month = número real de días del mes de `date`
   costo_fijo_diario = SUM(business_fixed_costs.amount WHERE recurrence='monthly') / days_in_month
                     + SUM(business_fixed_costs.amount WHERE recurrence='weekly') / 7

3. gasto_variable_dia = SUM(transactions.amount
                            WHERE transaction_date = date
                            AND expense_behavior = 'VARIABLE'
                            AND needs_human_review = false)

4. costo_total_dia = costo_fijo_diario + gasto_variable_dia

5. resultado_operativo_mxn = pos_inputs.total_sales - costo_total_dia

6. break_even_status = clasificar(resultado_operativo_mxn):
     > 0   → "ganancia"
     = 0   → "equilibrio"
     < 0   → "perdida"

7. fase_ciclo_vida = clasificar(business_age_months)
```

**Nota sobre gastos incompletos:** Si existen documentos del día con `needs_human_review = true`,
el `gasto_variable_dia` está subestimado. En ese caso agregar warning y continuar con los datos disponibles.

**Clasificación de ciclo de vida:**

| Rango (meses) | Fase                  | Expectativa de resultado |
|---------------|-----------------------|--------------------------|
| 0 – 2         | Luna de miel          | Pérdida aceptable        |
| 3 – 6         | Valle crítico         | Pérdida esperada         |
| 7 – 17        | Construcción lenta    | Break-even o leve pérdida|
| 18 – 24       | Break-even zone       | Ganancia esperada        |
| > 24          | Madurez               | Ganancia consistente     |

El `alert_level` se pondera según la fase: una pérdida en "Valle crítico" es `warning`,
la misma pérdida en "Madurez" es `critical`.

> **Limitación conocida (v1):** La fase "Madurez" aplica a cualquier negocio con > 24 meses,
> sin distinción entre 2 años y 10 años. Las expectativas de rentabilidad difieren
> significativamente. En versiones posteriores se deberá segmentar esta fase con
> sub-rangos (ej. 25–48 meses, 49–84 meses, > 84 meses) con umbrales de alerta diferenciados.

---

### B) Burn Rate Variable

```
burn_rate_variable_pct = (gasto_variable_dia / pos_inputs.total_sales) × 100
```

**Umbrales:**

| Burn rate variable | Status              |
|--------------------|---------------------|
| ≤ 35%              | `ok`                |
| 36% – 50%          | `warning`           |
| > 50%              | `critical`          |
| > 100%             | `critical` — reportar valor real, no capear |

El valor se reporta siempre como el ratio real (puede superar 100% si los gastos variables
superan las ventas del día — ej. compra de emergencia grande). No se capea.

Edge: `total_sales = 0` → `burn_rate_status: "incomplete_data"`, no calcular ratio.

---

### C) Detección de Anomalías

**C1 — Caída de ventas vs promedio móvil:**

```
dias_anteriores = pos_inputs WHERE date IN (date-7 días calendario ... date-1)
                               AND total_sales > 0   # excluye días de cierre

IF len(dias_anteriores) < 3 → ventas_status: "incomplete_data", delta: null
ELSE:
  promedio_7d = AVG(dias_anteriores.total_sales)
  delta_ventas_7d_pct = ((total_sales_hoy - promedio_7d) / promedio_7d) × 100
```

El promedio usa los días **anteriores** a `date` con ventas registradas (> 0).
No incluye el día actual. No usa "días hábiles" — usa días con ventas reales para
evitar contaminar el promedio con días de cierre.

| Delta ventas | Status              |
|--------------|---------------------|
| > -20%       | `ok`                |
| -20% a -35%  | `warning`           |
| < -35%       | `critical`          |

**C2 — CAPEX no categorizado:**
```
capex_sin_categorizar = COUNT(transactions
                              WHERE transaction_date = date
                              AND expense_behavior = 'CAPEX'
                              AND category IS NULL)
```
Si ≥ 1 → agregar warning. No bloquea el cálculo.

---

## Output — `NodeResult`

```python
NodeResult(
    node_id="N09",
    node_name="auditoria_financiera",
    status="success" | "timeout" | "error",
    result=AgentResult(
        module="auditoria_operativa",
        raw_result=FinancialAuditResult(
            fase_ciclo_vida=str,                # ej. "Valle crítico (Mes 4)"
            business_age_months=int,
            break_even_status=Literal["ganancia", "perdida", "equilibrio"],
            resultado_operativo_mxn=Decimal,    # positivo = ganancia, negativo = pérdida
            costo_fijo_diario=Decimal,
            gasto_variable_dia=Decimal,
            total_sales=Decimal,
            gastos_incompletos=bool,            # true si hay docs con needs_human_review
            burn_rate_variable_pct=Decimal | None,  # None si total_sales = 0
            burn_rate_status=Literal["ok", "warning", "critical", "incomplete_data"],
            delta_ventas_7d_pct=Decimal | None, # None si historial < 3 días
            ventas_status=Literal["ok", "warning", "critical", "incomplete_data"],
            capex_sin_categorizar=int,
            dias_historial_disponibles=int,     # cuántos días anteriores con ventas > 0
        ),
        copilot_phrase=str | None,              # None si LLM falla — no rompe el nodo
        archetype=str,
    ),
    warnings=list[str],                         # señales para N11 Consultor
    error_detail=str | None,
    duration_ms=int,
)
```

**Modelo Pydantic del `raw_result`:**

```python
class FinancialAuditResult(BaseModel):
    fase_ciclo_vida: str
    business_age_months: int = Field(ge=0)
    break_even_status: Literal["ganancia", "perdida", "equilibrio"]
    resultado_operativo_mxn: Decimal
    costo_fijo_diario: Decimal = Field(ge=0)
    gasto_variable_dia: Decimal = Field(ge=0)
    total_sales: Decimal = Field(ge=0)
    gastos_incompletos: bool
    burn_rate_variable_pct: Optional[Decimal]   # None si total_sales = 0
    burn_rate_status: Literal["ok", "warning", "critical", "incomplete_data"]
    delta_ventas_7d_pct: Optional[Decimal]      # None si historial < 3 días
    ventas_status: Literal["ok", "warning", "critical", "incomplete_data"]
    capex_sin_categorizar: int = Field(ge=0)
    dias_historial_disponibles: int = Field(ge=0)
```

---

### Reglas de generación de `warnings`

| Condición                                          | Warning agregado                                              |
|----------------------------------------------------|---------------------------------------------------------------|
| `burn_rate_variable_pct > 35%`                     | `"Burn rate variable superior al 35% ideal"`                  |
| `burn_rate_variable_pct > 100%`                    | `"Burn rate variable supera el 100% — gastos mayores que ventas"` |
| `delta_ventas_7d_pct < -20%`                       | `"Caída atípica de ventas vs promedio 7 días"`                |
| `break_even_status == "perdida"` en "Madurez"      | `"Pérdida operativa en negocio maduro"`                       |
| `capex_sin_categorizar >= 1`                       | `"CAPEX sin categorizar detectado"`                           |
| `burn_rate_status == "incomplete_data"`            | `"Sin datos de ventas — burn rate no calculable"`             |
| `gastos_incompletos == true`                       | `"Gastos del día incompletos — hay facturas pendientes de revisión"` |
| `business_fixed_costs` vacío                       | `"Sin gastos fijos registrados — break-even no confiable"`    |

---

## Generación de `copilot_phrase` (LLM)

El LLM recibe `FinancialAuditResult` completo + `archetype` + `context_tags` y genera
una frase CEO-framed siguiendo el Prompt Dictionary de S4.

**Reglas de la frase:**
- Debe mencionar la fase del ciclo de vida si es relevante
- Debe cuantificar en MXN cuando hay pérdida operativa
- PROHIBIDO: frases genéricas — debe ser específica al `raw_result`
- Si `burn_rate_status: "critical"` → incluir acción correctiva con plazo
- Si `gastos_incompletos: true` → mencionar que el análisis es parcial

**Ejemplo (Growth Hacker, Valle crítico):**
```
"Estás en el mes 4 — el valle crítico es normal, pero tu burn rate variable del 48%
está 13 puntos sobre el ideal. Si no lo corriges antes del mes 6, el break-even
se retrasa 2 meses más. Acción: auditar los 3 proveedores con mayor gasto esta semana."
```

---

## Acceptance Criteria

- WHEN `opening_date` no existe en `businesses` → `status: "error"`, `error_detail: "missing opening_date"`
- WHEN `total_sales = 0` → `burn_rate_status: "incomplete_data"`, `burn_rate_variable_pct: null`, agregar warning
- WHEN historial < 3 días con ventas > 0 → `ventas_status: "incomplete_data"`, `delta_ventas_7d_pct: null`
- WHEN `resultado_operativo < 0` en fase "Madurez" → warning `"Pérdida operativa en negocio maduro"`
- WHEN `resultado_operativo < 0` en fase "Valle crítico" → `warning` (no `critical`) — pérdida esperada
- WHEN `burn_rate_variable_pct > 50%` → `burn_rate_status: "critical"`, `copilot_phrase` incluye acción con plazo
- WHEN `burn_rate_variable_pct > 100%` → reportar valor real, agregar warning adicional, no capear
- WHEN `capex_sin_categorizar >= 1` → agregar warning, no bloquear cálculo
- WHEN documentos del día con `needs_human_review: true` → `gastos_incompletos: true`, agregar warning, continuar con datos disponibles
- WHEN `costo_fijo_diario` calculado → usar `days_in_month(date)` como divisor, no 30 fijo
- WHEN promedio móvil calculado → usar solo días **anteriores** a `date` con `total_sales > 0`
- WHEN LLM falla → `copilot_phrase: null`, `status: "success"` — `raw_result` es suficiente para N11
- WHEN timeout → N06 marca `status: "timeout"`, `duration_ms ≈ node_timeouts.n09_gastos`

---

## Edge Cases

- `opening_date` en el futuro → `business_age_months: 0`, fase "Luna de miel"
- Día sin transacciones VARIABLE → `gasto_variable_dia: 0`, `burn_rate_variable_pct: 0`, `burn_rate_status: "ok"`
- `business_fixed_costs` vacío → `costo_fijo_diario: 0`, agregar warning, continuar
- Día festivo con ventas altas → `context_tags.evento = "festivo"` — el LLM pondera el contexto, la heurística reporta el valor real sin ajuste
- Negocio con solo gastos fijos (sin facturas del día) → `gasto_variable_dia: 0`, calcular normalmente
- `opening_date` = `date` (primer día de operación) → `business_age_months: 0`, fase "Luna de miel", `dias_historial_disponibles: 0`, `ventas_status: "incomplete_data"`

---

## Correctness Properties (PBT)

| ID | Propiedad |
|----|-----------|
| P1 | `node_id: "N09"` y `node_name: "auditoria_financiera"` siempre presentes en `NodeResult` |
| P2 | `burn_rate_variable_pct` es `null` cuando `total_sales = 0` — nunca calculado |
| P3 | `delta_ventas_7d_pct` es `null` cuando `dias_historial_disponibles < 3` — nunca calculado |
| P4 | `resultado_operativo_mxn = total_sales - costo_fijo_diario - gasto_variable_dia` siempre |
| P5 | `break_even_status == "perdida"` ↔ `resultado_operativo_mxn < 0` siempre |
| P6 | Fase "Valle crítico" con pérdida → `warnings` nunca incluye `"Pérdida operativa en negocio maduro"` |
| P7 | `copilot_phrase: null` no cambia `status` a `"error"` — el nodo sigue siendo `"success"` |
| P8 | `warnings` es `[]` cuando no hay condiciones de alerta — nunca `null` |
| P9 | `business_age_months` siempre entero ≥ 0 |
| P10| `costo_fijo_diario` calculado con `days_in_month(date)` — nunca con divisor fijo 30 |
| P11| Promedio móvil calculado solo con días anteriores a `date` — nunca incluye el día actual |
| P12| `burn_rate_variable_pct` reporta valor real aunque supere 100% — nunca capeado |
