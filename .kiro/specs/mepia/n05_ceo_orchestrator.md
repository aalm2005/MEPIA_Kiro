# N05 — CEO Orchestrator

**Capa:** CEO Layer | **Anterior:** S4 Auditoría IA | **Siguiente:** N06 Orquestador ADK (Layer 2)
**Archivo de implementación:** `agents/ceo_orchestrator.py`
**Enfoque:** API-First / Headless — stateless, sin dependencias de UI

---

## Responsabilidad

Punto de entrada único del sistema. Recibe la solicitud de auditoría del cliente, coordina
la ejecución del pipeline Sequential (S1→S4) y decide si escalar a Layer 2 (Parallel).

```
Cliente
  │
  └─ POST /orchestrator/run
        │
        ├─ Verificar prerequisitos (S1 completo, S2 active_metrics > 0)
        ├─ Ejecutar S3 → CalcResult[]
        ├─ Ejecutar S4 → AuditInsight[]
        ├─ Evaluar si escalar a Layer 2
        └─ Retornar OrchestratorResult
```

No ejecuta lógica de negocio — delega a cada nodo y agrega resultados.

---

## Endpoint principal

### `POST /orchestrator/run`

Dispara el pipeline completo desde S3 hasta S4 para un negocio y fecha dados.
S1 y S2 deben haberse ejecutado previamente (ingesta + gatekeeper).

**Request body — `OrchestratorRunPayload`:**

```python
class OrchestratorRunPayload(BaseModel):
    business_id: UUID
    date: date
    archetype: Literal[
        "Operative Genius", "Product Purist", "Growth Hacker"
    ] = "Operative Genius"
    escalate_to_parallel: bool = True   # si False, solo corre Sequential
```

**Response 200:**
```json
{
  "run_id": "uuid-v4",
  "business_id": "uuid-v4",
  "date": "2024-01-15",
  "archetype": "Operative Genius",
  "pipeline_status": "completed" | "partial" | "escalated",
  "sequential_results": {
    "active_metrics": ["cash_reconciliation", "daily_break_even"],
    "calc_results": [ /* CalcResult[] */ ],
    "audit_insights": [ /* AuditInsight[] */ ]
  },
  "escalation": {
    "triggered": true,
    "reason": "critical_alerts_detected",
    "layer2_run_id": "uuid-v4"   // null si escalate_to_parallel: false
  },
  "dormant_metrics": [
    { "metric": "inventory_variance", "missing": ["recipes"] }
  ],
  "completed_at": "2024-01-15T22:10:00Z"
}
```

**Códigos de error:**

| HTTP | Condición                                                              |
|------|------------------------------------------------------------------------|
| 404  | `business_id` no existe                                                |
| 409  | S2 no ha corrido o todas las métricas en `dormant`/`blocked` — pipeline no puede iniciar |
| 422  | `archetype` inválido                                                   |
| 422  | `date` en el futuro                                                    |
| 503  | Fallo interno en S3 o S4 — incluye detalle del nodo que falló          |

---

### `GET /orchestrator/status/{run_id}`

Consulta el estado de una ejecución en curso o completada.

**Response 200:**
```json
{
  "run_id": "uuid-v4",
  "business_id": "uuid-v4",
  "date": "2024-01-15",
  "pipeline_status": "running" | "completed" | "partial" | "failed",
  "current_node": "S4",
  "completed_at": "2024-01-15T22:10:00Z"   // null si aún en curso
}
```

---

## Lógica de escalación a Layer 2

El orquestador evalúa los `AuditInsight[]` de S4 y decide si escalar automáticamente.

| Condición                                          | Acción                          |
|----------------------------------------------------|---------------------------------|
| ≥ 1 insight con `alert_level: "critical"`          | Escalar a Layer 2 automáticamente |
| Todos los insights en `"info"` o `"warning"`       | No escalar (solo Sequential)    |
| `escalate_to_parallel: false` en request           | Nunca escalar, ignorar alertas  |

Cuando escala: dispara `POST /layer2/run` internamente con el `run_id` del Sequential como contexto.

Si N06 retorna HTTP 503 (`gather_status: "failed"`):
- Actualizar `pipeline_status` a `"failed"` en `OrchestratorResult`
- Persistir error en `audit_results` con `module: "N06"` y detalle del fallo
- No reintentar automáticamente — retornar HTTP 503 al cliente con detalle
- El cliente puede reintentar vía `POST /orchestrator/run` en una nueva sesión

---

## Modelo de datos — `OrchestratorResult`

```python
class EscalationInfo(BaseModel):
    triggered: bool
    reason: Optional[str]           # "critical_alerts_detected" | "manual_override" | null
    layer2_run_id: Optional[UUID]

class OrchestratorResult(BaseModel):
    run_id: UUID
    business_id: UUID
    date: date
    archetype: Literal["Operative Genius", "Product Purist", "Growth Hacker"]
    pipeline_status: Literal["completed", "partial", "escalated", "failed"]
    sequential_results: dict        # { active_metrics, calc_results, audit_insights }
    escalation: EscalationInfo
    dormant_metrics: list[dict]
    completed_at: datetime
```

---

## Prerequisitos de ejecución

Antes de correr S3, el orquestador verifica:

```
1. business_id existe en businesses
2. metric_status para business_id + date tiene al menos 1 status = "active"
3. No hay documentos con needs_human_review = true sin resolver para esa fecha
```

Si alguna condición falla → HTTP 409 con detalle de qué falta.

---

## Persistencia

Cada ejecución se registra en `audit_results`:

| Campo           | Valor                                      |
|-----------------|--------------------------------------------|
| `run_id`        | UUID de la ejecución                       |
| `business_id`   | FK → businesses                            |
| `date`          | Fecha auditada                             |
| `archetype`     | Arquetipo usado                            |
| `module`        | Nombre del nodo (S3, S4, etc.)             |
| `raw_result`    | JSON serializado del resultado             |
| `copilot_phrase`| Frase del insight de S4                    |

---

## Acceptance Criteria

- WHEN S2 no ha corrido para `business_id + date` → HTTP 409, no ejecutar pipeline
- WHEN todas las métricas en `dormant` → HTTP 409 con lista de `missing_fields`
- WHEN S3 falla en una métrica → continuar con las demás, incluir error en `calc_results`
- WHEN S4 produce ≥ 1 `critical` y `escalate_to_parallel: true` → `escalation.triggered: true`
- WHEN `escalate_to_parallel: false` → `escalation.triggered: false` siempre
- WHEN pipeline completa sin errores → `pipeline_status: "completed"`
- WHEN pipeline completa con métricas `dormant` → `pipeline_status: "partial"`
- WHEN escaló a Layer 2 → `pipeline_status: "escalated"`, `layer2_run_id` no nulo

---

## Correctness Properties (PBT)

| ID | Propiedad |
|----|-----------|
| P1 | `run_id`, `pipeline_status`, `completed_at` siempre no nulos en `OrchestratorResult` |
| P2 | `escalation.triggered: true` → `layer2_run_id` no nulo |
| P3 | `escalation.triggered: false` → `layer2_run_id` es null siempre |
| P4 | `escalate_to_parallel: false` en request → `escalation.triggered` siempre false |
| P5 | S2 sin métricas `active` → HTTP 409, ningún nodo S3/S4 ejecutado |
| P6 | Fallo en S3 para métrica X → otras métricas siguen calculándose (no falla total) |
