# N10 — Onboarding de Identidad del Negocio

**Capa:** Transversal (prerequisito de Layer 3) | **Endpoint:** `POST /business/{id}/onboarding`
**Archivo de implementación:** `api/main.py`
**Depende de:** `businesses` (debe existir), `mepia_memory` (escribe chunk `node_origin: "onboarding"`)
**Bloquea:** Layer 3 no puede ejecutarse si este setup no está completo

---

## Responsabilidad

Inyectar el "Lente del CEO" en `mepia_memory` y registrar los parámetros de auditoría
del negocio. Este endpoint es el **prerequisito obligatorio** para cualquier ejecución
de Layer 3. Sin él, el sistema no tiene contexto de identidad ni umbrales de tolerancia
para el CFO Forense.

No es solo un registro de marca — es la configuración del motor de auditoría.

---

## Endpoint

### `POST /business/{business_id}/onboarding`

**Path param:** `business_id` — UUID del negocio ya creado en `businesses`

**Request body — `OnboardingIdentityPayload`:**

```python
class AuditTolerances(BaseModel):
    """Umbrales que el CFO Forense usa para clasificar anomalías."""
    max_cash_discrepancy_pct: float = Field(
        gt=0, le=1,
        description="Diferencia máxima aceptable entre POS y caja física. Ej: 0.02 = 2%"
    )
    max_cash_discrepancy_abs: Decimal = Field(
        ge=0,
        description="Diferencia absoluta máxima en MXN. Ej: 150.00"
    )
    # Regla: se usa el umbral que sea MÁS PERMISIVO (OR, no AND)
    # Si diff < 2% O diff < $150 → no es anomalía crítica

    margin_warning_threshold: float = Field(
        gt=0, le=1,
        description="Margen neto mínimo esperado. Por debajo → warning. Ej: 0.15 = 15%"
    )
    margin_critical_threshold: float = Field(
        gt=0, le=1,
        description="Margen neto crítico. Por debajo → alerta roja. Ej: 0.08 = 8%"
    )

    cost_spike_threshold_pct: float = Field(
        gt=0, le=1,
        description="Incremento de costo que dispara alerta. Ej: 0.10 = 10% sobre período anterior"
    )


class ExpectedCostStructure(BaseModel):
    """Estructura de costos fijos esperada — base para detectar desviaciones."""
    concept: str
    expected_monthly_amount: Decimal = Field(ge=0)
    tolerance_pct: float = Field(
        ge=0, le=1,
        description="Variación aceptable sobre el monto esperado. Ej: 0.05 = ±5%"
    )
    expense_behavior: Literal["FIXED", "VARIABLE", "CAPEX"]


class AuditRules(BaseModel):
    """Reglas de auditoría específicas del negocio."""
    red_alert_triggers: list[str] = Field(
        description=(
            "Condiciones que siempre generan alerta roja, sin importar umbrales. "
            "Ej: ['caja_negativa', 'ventas_cero_dia_laboral', 'proveedor_no_registrado']"
        )
    )
    ignored_anomaly_types: list[str] = Field(
        default=[],
        description=(
            "Tipos de anomalía que el negocio acepta como normales. "
            "Ej: ['cost_spike'] si el negocio tiene precios de insumos muy volátiles."
        )
    )
    audit_frequency: Literal["daily", "weekly"] = "daily"


class BrandIdentity(BaseModel):
    """Identidad de marca — el 'Lente del CEO' que N11 usa para el tono del reporte."""
    brand_voice: str = Field(
        max_length=500,
        description=(
            "Descripción del tono y valores del negocio. "
            "Ej: 'hospitalidad invisible, espacio seguro, sin fricción'"
        )
    )
    prohibited_recommendations: list[str] = Field(
        description=(
            "Tipos de recomendaciones que contradicen la identidad. "
            "Ej: ['fidelización ostentosa', 'marketing agresivo', 'mecánicas de casino']"
        )
    )
    priority_focus: Literal["efficiency", "quality", "growth"] = Field(
        description="Foco principal del dueño — mapea al CEO Archetype"
    )


class OnboardingIdentityPayload(BaseModel):
    brand_identity: BrandIdentity
    audit_tolerances: AuditTolerances
    expected_cost_structure: list[ExpectedCostStructure] = Field(min_length=1)
    audit_rules: AuditRules
```

**Response 201 — Creado:**
```json
{
  "business_id": "uuid-v4",
  "onboarding_status": "complete",
  "memory_chunk_id": "uuid-v4",
  "audit_config_stored": true,
  "completed_at": "2024-01-15T10:00:00Z"
}
```

**Códigos de error:**

| HTTP | Condición |
|------|-----------|
| 404  | `business_id` no existe en `businesses` |
| 409  | Onboarding ya completado — usar `PUT` para actualizar |
| 422  | Validación Pydantic fallida (ej. `max_cash_discrepancy_pct > 1`) |
| 503  | `mepia_memory` no disponible |

---

### `PUT /business/{business_id}/onboarding`

Actualiza la configuración de onboarding. Mismo body que `POST`.
Crea un nuevo chunk en `mepia_memory` (el anterior queda como historial).
N10 Context Builder siempre recupera el más reciente (`ORDER BY created_at DESC LIMIT 1`).

---

### `GET /business/{business_id}/onboarding/status`

Verifica si el onboarding está completo antes de disparar Layer 3.

**Response 200:**
```json
{
  "business_id": "uuid-v4",
  "onboarding_complete": true,
  "completed_at": "2024-01-15T10:00:00Z",
  "has_brand_identity": true,
  "has_audit_tolerances": true,
  "has_cost_structure": true
}
```

---

## Bloqueo de Layer 3

**Regla de negocio crítica:** Si `onboarding_complete: false`, el endpoint
`POST /api/audit/layer3/run` debe retornar HTTP 412 (Precondition Failed).

```python
# En build_initial_state() — verificación previa al grafo
onboarding = await db.fetchone(
    "SELECT id FROM mepia_memory "
    "WHERE business_id = :bid AND metadata->>'node_origin' = 'onboarding' "
    "ORDER BY created_at DESC LIMIT 1",
    {"bid": business_id}
)
if not onboarding:
    raise HTTPException(
        status_code=412,
        detail={
            "error": "onboarding_required",
            "message": "El negocio no tiene configuración de auditoría. "
                       "Completar POST /business/{id}/onboarding antes de ejecutar Layer 3.",
            "setup_url": f"/business/{business_id}/onboarding"
        }
    )
```

---

## Persistencia

El onboarding escribe en dos lugares:

**1. `mepia_memory` — chunk de identidad (vía MemoryService):**
```python
MemoryChunk(
    business_id=business_id,
    source_audit_run_id=None,      # nullable — onboarding no tiene run previo
    node_origin="onboarding",
    date=today.isoformat(),
    content=f"""
        IDENTIDAD DE MARCA:
        {payload.brand_identity.brand_voice}

        PROHIBIDO EN RECOMENDACIONES:
        {', '.join(payload.brand_identity.prohibited_recommendations)}

        FOCO PRINCIPAL: {payload.brand_identity.priority_focus}

        UMBRALES DE AUDITORÍA:
        - Discrepancia caja máxima: {payload.audit_tolerances.max_cash_discrepancy_pct*100}%
          o ${payload.audit_tolerances.max_cash_discrepancy_abs} MXN (el más permisivo)
        - Margen warning: {payload.audit_tolerances.margin_warning_threshold*100}%
        - Margen crítico: {payload.audit_tolerances.margin_critical_threshold*100}%
        - Spike de costo: {payload.audit_tolerances.cost_spike_threshold_pct*100}%

        ALERTAS ROJAS AUTOMÁTICAS:
        {', '.join(payload.audit_rules.red_alert_triggers)}
    """,
    archetype=None,                # identidad fija, independiente del arquetipo
    quality_approved=True
)
```

**2. `business_fixed_costs` — estructura de costos esperada:**
Cada `ExpectedCostStructure` se persiste como fila en `business_fixed_costs`
con `is_active: true`. Las filas anteriores se marcan `is_active: false`.

---

## Acceptance Criteria

- WHEN `POST /business/{id}/onboarding` con payload válido → chunk en `mepia_memory` con `node_origin: "onboarding"`, HTTP 201
- WHEN `POST /api/audit/layer3/run` sin onboarding previo → HTTP 412 con `error: "onboarding_required"`
- WHEN `PUT /business/{id}/onboarding` → nuevo chunk en `mepia_memory`, filas anteriores en `business_fixed_costs` marcadas `is_active: false`
- WHEN `max_cash_discrepancy_pct > 1` → HTTP 422
- WHEN `expected_cost_structure` vacío → HTTP 422
- WHEN `margin_critical_threshold >= margin_warning_threshold` → HTTP 422

---

## Edge Cases

- Negocio nuevo sin transacciones: onboarding válido, Layer 3 puede ejecutarse pero `time_series.periodos` estará vacío
- `red_alert_triggers` vacío: permitido — el negocio no tiene reglas adicionales
- Onboarding actualizado durante un run activo de Layer 3: el run usa el chunk anterior (el que estaba al momento de `build_initial_state`)

---

## Archivos relacionados de este nodo
- `n10_context_builder.md` — consume el chunk de onboarding vía SQL directo
- `mem_memory_layer.md` — `MemoryService.store_memory()` + `MemoryChunk`
- `db_schema.md` — `mepia_memory`, `business_fixed_costs`
- `_glossary.md` — `OnboardingPayload` (actualizar con `OnboardingIdentityPayload`)
- `api_layer3.md` — bloqueo HTTP 412 si onboarding incompleto
