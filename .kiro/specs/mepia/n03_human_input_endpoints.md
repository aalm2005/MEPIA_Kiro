# N03 — Human Input Endpoints (API-First)

**Capa:** Sequential | **Parte de:** S1 Ingesta | **Alimenta:** S2 Gatekeeper
**Archivos relacionados:** `api/main.py`, `db_schema.md`
**Enfoque:** API-First / Headless — contratos REST para intervención humana sin dependencia de UI

---

## Contexto

Estos endpoints son los "cables sueltos" que permiten a cualquier cliente (UI futura, script,
integración externa) enviar datos que requieren intervención humana. Sin ellos, S2 mantiene
las métricas dependientes en estado `dormant` o `blocked`.

| Endpoint group              | Desbloquea en S2                                      |
|-----------------------------|-------------------------------------------------------|
| `expense_behavior` confirm  | `daily_break_even`, `operative_cost_margin`           |
| `cash_counts` submit        | `cash_reconciliation`                                 |
| `onboarding` register       | Todas las métricas (prerequisito global)              |

---

## 1. Expense Behavior — Confirmación de tipo de gasto

### Contexto

Cuando S1 extrae una transacción de factura, `expense_behavior` queda como `null`.
S3 nunca asume este valor — solo opera sobre gastos confirmados explícitamente.

### `PATCH /transactions/{transaction_id}/expense-behavior`

Confirma o corrige la clasificación de un gasto extraído.

**Request body:** `application/json`

```json
{
  "expense_behavior": "FIXED",
  "confirmed_by": "user-uuid"
}
```

**Modelo Pydantic — `ExpenseBehaviorPayload`:**

```python
class ExpenseBehaviorPayload(BaseModel):
    expense_behavior: Literal["FIXED", "VARIABLE", "CAPEX"]
    confirmed_by: UUID
```

**Response 200:**
```json
{
  "transaction_id": "uuid-v4",
  "expense_behavior": "FIXED",
  "confirmed_by": "user-uuid",
  "confirmed_at": "2024-01-15T10:30:00Z",
  "gatekeeper_triggered": true
}
```

`gatekeeper_triggered: true` indica que S2 fue re-evaluado tras la confirmación.

**Códigos de error:**

| HTTP | Condición                                                  |
|------|------------------------------------------------------------|
| 404  | `transaction_id` no existe                                 |
| 422  | `expense_behavior` no es `FIXED`, `VARIABLE` ni `CAPEX`   |
| 409  | Transacción ya tiene `expense_behavior` confirmado (usar `force: true` para sobreescribir) |

**Override opcional:**

```json
{
  "expense_behavior": "VARIABLE",
  "confirmed_by": "user-uuid",
  "force": true
}
```

---

### `GET /transactions/pending-review`

Lista todas las transacciones del negocio con `expense_behavior: null` para que el cliente
sepa qué confirmaciones están pendientes.

**Query params:**

| Param         | Tipo   | Default | Descripción                        |
|---------------|--------|---------|------------------------------------|
| `business_id` | UUID   | —       | Requerido                          |
| `date`        | date   | hoy     | Filtrar por fecha de transacción   |

**Response 200:**
```json
{
  "pending": [
    {
      "transaction_id": "uuid-v4",
      "supplier_name": "CFE",
      "concept": "Electricidad enero",
      "amount": 3200.00,
      "transaction_date": "2024-01-15",
      "suggested_behavior": "FIXED"
    }
  ],
  "total": 1
}
```

`suggested_behavior` es una inferencia del sistema basada en `supplier_name` / `concept` —
el cliente puede aceptarla o ignorarla. Nunca se persiste automáticamente.

---

## 2. Cash Counts — Conteo físico del cajón

### Contexto

`calc_cash_reconciliation` en S3 necesita el conteo físico del cajón al cierre del día.
Este endpoint es el único mecanismo para ingresar ese dato al sistema.

### `POST /cash-counts`

Registra el conteo físico del cajón para un negocio y fecha.

**Request body:** `application/json`

```json
{
  "business_id": "uuid-v4",
  "date": "2024-01-15",
  "initial_float": 500.00,
  "actual_counted": 4820.00,
  "cash_payouts": 350.00,
  "recorded_by": "user-uuid"
}
```

**Modelo Pydantic — `CashCountPayload`:**

```python
class CashCountPayload(BaseModel):
    business_id: UUID
    date: date
    initial_float: Decimal = Field(ge=0, decimal_places=2)
    actual_counted: Decimal = Field(ge=0, decimal_places=2)
    cash_payouts: Decimal = Field(ge=0, decimal_places=2, default=Decimal("0"))
    recorded_by: UUID
```

**Response 201:**
```json
{
  "cash_count_id": "uuid-v4",
  "business_id": "uuid-v4",
  "date": "2024-01-15",
  "initial_float": 500.00,
  "actual_counted": 4820.00,
  "cash_payouts": 350.00,
  "recorded_by": "user-uuid",
  "created_at": "2024-01-15T22:05:00Z",
  "gatekeeper_triggered": true
}
```

**Códigos de error:**

| HTTP | Condición                                                        |
|------|------------------------------------------------------------------|
| 404  | `business_id` no existe                                          |
| 409  | Ya existe un `cash_count` para `business_id + date` (usar `PUT` para actualizar) |
| 422  | Validación Pydantic fallida                                      |
| 422  | `date` en el futuro                                              |

---

### `PUT /cash-counts/{cash_count_id}`

Actualiza un conteo ya registrado (corrección antes del cierre contable).

**Request body:** mismo esquema que `POST`, todos los campos opcionales excepto `recorded_by`.

**Response 200:** mismo esquema de respuesta que `POST 201`.

**Códigos de error:**

| HTTP | Condición                              |
|------|----------------------------------------|
| 404  | `cash_count_id` no existe              |
| 422  | Validación Pydantic fallida            |

---

### `GET /cash-counts`

Consulta el estado del conteo para un negocio y fecha.

**Query params:**

| Param         | Tipo | Default | Descripción      |
|---------------|------|---------|------------------|
| `business_id` | UUID | —       | Requerido        |
| `date`        | date | hoy     | Fecha de consulta|

**Response 200 — conteo registrado:**
```json
{
  "cash_count_id": "uuid-v4",
  "date": "2024-01-15",
  "initial_float": 500.00,
  "actual_counted": 4820.00,
  "cash_payouts": 350.00,
  "recorded_by": "user-uuid",
  "created_at": "2024-01-15T22:05:00Z"
}
```

**Response 200 — sin conteo:**
```json
{
  "cash_count_id": null,
  "date": "2024-01-15",
  "status": "pending",
  "message": "No hay conteo registrado para esta fecha. cash_reconciliation en dormant."
}
```

---

## 3. Onboarding — Registro inicial del negocio

### Contexto

Prerequisito global del sistema. Sin un `business_id` válido con al menos 1 gasto fijo
registrado, ninguna métrica puede activarse en S2.

### `POST /onboarding/business`

Crea el negocio y sus gastos fijos iniciales en una sola operación atómica.

**Request body:** `application/json`

```json
{
  "business_name": "Café Mepia",
  "industry_sector": "cafetería",
  "currency": "MXN",
  "operating_hours": {
    "open": "08:00",
    "close": "22:00"
  },
  "fixed_costs": [
    {
      "concept": "Renta",
      "amount": 18000.00,
      "recurrence": "monthly",
      "expense_behavior": "FIXED"
    },
    {
      "concept": "CFE",
      "amount": 3200.00,
      "recurrence": "monthly",
      "expense_behavior": "FIXED"
    }
  ]
}
```

**Modelo Pydantic — `OnboardingPayload`:**

```python
class OperatingHours(BaseModel):
    open: str = Field(pattern=r"^\d{2}:\d{2}$")
    close: str = Field(pattern=r"^\d{2}:\d{2}$")

class FixedCostItem(BaseModel):
    concept: str = Field(min_length=1, max_length=255)
    amount: Decimal = Field(gt=0, decimal_places=2)
    recurrence: Literal["monthly", "weekly"]
    expense_behavior: Literal["FIXED", "VARIABLE", "CAPEX"]

class OnboardingPayload(BaseModel):
    business_name: str = Field(min_length=1, max_length=255)
    industry_sector: str = Field(min_length=1, max_length=100)
    currency: str = Field(default="MXN", pattern=r"^[A-Z]{3}$")  # ISO 4217
    operating_hours: OperatingHours
    fixed_costs: list[FixedCostItem] = Field(min_length=1)        # al menos 1 gasto fijo
```

**Response 201:**
```json
{
  "business_id": "uuid-v4",
  "business_name": "Café Mepia",
  "fixed_costs_created": 2,
  "created_at": "2024-01-15T09:00:00Z"
}
```

**Códigos de error:**

| HTTP | Condición                                                    |
|------|--------------------------------------------------------------|
| 422  | `fixed_costs` vacío (mínimo 1 requerido)                     |
| 422  | `currency` no es ISO 4217 de 3 letras mayúsculas             |
| 422  | `operating_hours` con formato inválido                       |
| 409  | `business_name` ya existe (duplicado)                        |

**Atomicidad:** si la inserción de cualquier `fixed_cost` falla, se hace rollback completo —
ni `businesses` ni `business_fixed_costs` quedan creados parcialmente.

---

## 4. Daily Context — Tags del día

### Contexto

S4 usa `daily_context.tags` para ponderar alertas. Sin este dato, todas las alertas se tratan
con `context_weight: "normal"` — ninguna métrica se bloquea, pero se pierde la ponderación contextual.

### `POST /daily-context`

Registra los tags de contexto para un negocio y fecha.

**Request body — `DailyContextPayload`:**

```python
class DailyContextPayload(BaseModel):
    business_id: UUID
    date: date
    tags: DailyContextTags

class DailyContextTags(BaseModel):
    clima: Optional[Literal["lluvia", "calor", "frio"]] = None
    equipo: Optional[Literal["falla_maquina", "mantenimiento"]] = None
    evento: Optional[Literal["festivo", "obra_vial", "promocion"]] = None
    personal: Optional[Literal["falta_staff", "capacitacion"]] = None
    otros: Optional[str] = Field(default=None, max_length=500)
```

Regla: campos no enviados → `null`. Nunca string vacío.

**Response 201:**
```json
{
  "context_id": "uuid-v4",
  "business_id": "uuid-v4",
  "date": "2024-01-15",
  "tags": { "clima": "lluvia", "equipo": null, "evento": null, "personal": null, "otros": null },
  "created_at": "2024-01-15T22:00:00Z"
}
```

**Códigos de error:**

| HTTP | Condición                                          |
|------|----------------------------------------------------|
| 404  | `business_id` no existe                            |
| 409  | Ya existe contexto para `business_id + date` (usar `PUT` para actualizar) |
| 422  | Valor de tag fuera del enum permitido              |

### `PUT /daily-context/{context_id}`

Actualiza los tags de un contexto ya registrado.

**Request body:** mismo esquema `DailyContextPayload`. **Response 200:** mismo esquema que `POST 201`.

---

## Acceptance Criteria

**expense_behavior:**
- WHEN `PATCH` con valor válido → `expense_behavior` actualizado, S2 re-evaluado
- WHEN `PATCH` sobre transacción ya confirmada sin `force: true` → HTTP 409
- WHEN `GET /pending-review` → solo transacciones con `expense_behavior: null` del negocio

**cash_counts:**
- WHEN `POST` exitoso → registro en `cash_counts`, `gatekeeper_triggered: true`
- WHEN `POST` duplicado para mismo `business_id + date` → HTTP 409
- WHEN `date` en el futuro → HTTP 422
- WHEN `GET` sin conteo registrado → `status: "pending"`, no HTTP 404

**onboarding:**
- WHEN `POST` exitoso → `businesses` + mínimo 1 `business_fixed_costs` creados atómicamente
- WHEN `fixed_costs` vacío → HTTP 422
- WHEN falla parcial en `fixed_costs` → rollback total, HTTP 500 con detalle

**daily_context:**
- WHEN `POST` exitoso → tags persistidos con `null` en campos no enviados, nunca string vacío
- WHEN valor de tag fuera de enum → HTTP 422
- WHEN `POST` duplicado para mismo `business_id + date` → HTTP 409
- WHEN no existe contexto para la fecha → S4 usa `context_weight: "normal"` en todas las alertas

---

## Correctness Properties (PBT)

| ID | Propiedad |
|----|-----------|
| P1 | `PATCH expense_behavior` con valor inválido → siempre HTTP 422, `expense_behavior` no modificado |
| P2 | `POST /cash-counts` con misma `business_id + date` dos veces → exactamente 1 registro en DB |
| P3 | `POST /onboarding` con `fixed_costs: []` → HTTP 422, ningún registro creado en ninguna tabla |
| P4 | `POST /onboarding` exitoso → `fixed_costs_created` == `len(fixed_costs)` en el payload |
| P5 | `GET /cash-counts` sin conteo → respuesta 200 con `cash_count_id: null`, nunca 404 |
| P6 | `gatekeeper_triggered: true` en respuesta → `metric_status` actualizado para `business_id + date` |
| P7 | `POST /daily-context` con tag fuera de enum → HTTP 422, ningún registro creado |
| P8 | `POST /daily-context` exitoso → todos los campos no enviados son `null`, nunca string vacío |
