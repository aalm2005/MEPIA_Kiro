# API Layer 3 — Endpoint Disparador

**Archivo de implementación:** `api/main.py`
**Grafo invocado:** `agents/layer3_graph.py` → `layer3_app`
**Patrón:** Endpoint REST asíncrono — construye estado inicial e invoca el grafo

---

## Responsabilidad

Este endpoint es el único punto de entrada externo para ejecutar el pipeline de
Layer 3 (generación del informe final). Recibe el `audit_run_id` del frontend,
consulta la base de datos para reconstruir el contexto de Layer 2, construye el
`Layer3State` inicial y dispara el grafo compilado.

**Layer 3 NO es llamado por N06 internamente.** Está desacoplado y se dispara
de forma explícita desde el frontend o desde un worker asíncrono.

---

## Endpoint

### `POST /api/audit/layer3/run`

**Request body — `Layer3RunPayload`:**

```python
class Layer3RunPayload(BaseModel):
    audit_run_id: str    # UUID del run de Layer 2 (layer2_run_id)
                         # El endpoint lo usa para recuperar el contexto de Supabase
```

**Response 202 — Aceptado:**
```json
{
  "layer3_run_id": "uuid-v4",
  "audit_run_id":  "uuid-v4",
  "status":        "running",
  "started_at":    "2024-01-15T22:20:00Z"
}
```

> El endpoint responde 202 inmediatamente. El grafo corre de forma asíncrona.
> El frontend hace polling a `GET /api/audit/layer3/status/{layer3_run_id}`
> para conocer el resultado.

**Códigos de error:**

| HTTP | Condición |
|------|-----------|
| 404  | `audit_run_id` no existe en `audit_results` |
| 409  | Ya existe un `layer3_run_id` para este `audit_run_id` — idempotencia |
| 422  | `audit_run_id` inválido (no es UUID) |
| 503  | Supabase no disponible al construir el estado inicial |

---

### `GET /api/audit/layer3/status/{layer3_run_id}`

Polling del frontend para conocer el estado del grafo en ejecución.

**Response 200 — En curso:**
```json
{
  "layer3_run_id": "uuid-v4",
  "status":        "running",
  "current_node":  "n11_consultor",
  "intentos_critico": 1,
  "started_at":    "2024-01-15T22:20:00Z",
  "completed_at":  null
}
```

**Response 200 — Completado:**
```json
{
  "layer3_run_id":  "uuid-v4",
  "status":         "completed",
  "draft_status":   "approved" | "approved_with_warning",
  "current_node":   "END",
  "intentos_critico": 0,
  "started_at":     "2024-01-15T22:20:00Z",
  "completed_at":   "2024-01-15T22:22:15Z"
}
```

**Response 200 — Fallido:**
```json
{
  "layer3_run_id": "uuid-v4",
  "status":        "failed",
  "error_detail":  "N11 LLM timeout after 30s",
  "started_at":    "2024-01-15T22:20:00Z",
  "completed_at":  "2024-01-15T22:20:31Z"
}
```

**Códigos de error:**

| HTTP | Condición |
|------|-----------|
| 404  | `layer3_run_id` no existe |

---

### `GET /api/audit/layer3/result/{layer3_run_id}`

Recupera el `FinalReport` completo una vez que el grafo completó.

**Response 200:**
```json
{
  "layer3_run_id":           "uuid-v4",
  "business_id":             "uuid-v4",
  "date":                    "2024-01-15",
  "archetype":               "Operative Genius",
  "executive_summary":       "string",
  "operational_narrative_md":"string (Markdown)",
  "pragmatic_actions": [
    { "action": "string", "priority": "immediate", "owner": "dueño" }
  ],
  "draft_status":            "approved",
  "model_used":              "claude-3-5-sonnet-20241022",
  "intentos_critico":        0,
  "quality_warnings":        [],
  "finalized_at":            "2024-01-15T22:22:15Z"
}
```

**Códigos de error:**

| HTTP | Condición |
|------|-----------|
| 404  | `layer3_run_id` no existe |
| 409  | El grafo aún no completó — usar `/status` primero |

---

## Construcción del Estado Inicial

El endpoint consulta Supabase para reconstruir el contexto antes de invocar el grafo:

```python
async def build_initial_state(audit_run_id: str, db) -> Layer3State:
    """
    Construye el Layer3State inicial consultando audit_results.

    1. Recupera el registro de Layer 2 (layer2_run_id, sequential_run_id,
       business_id, date, archetype) desde audit_results WHERE run_id = audit_run_id
    2. Genera un nuevo layer3_run_id
    3. Retorna el estado inicial con campos de control en sus valores por defecto
    """
    row = await db.fetchone(
        "SELECT * FROM audit_results WHERE run_id = :run_id AND node_id = 'N06'",
        {"run_id": audit_run_id}
    )
    if not row:
        raise HTTPException(status_code=404, detail="audit_run_id no encontrado")

    return {
        "layer3_run_id":    str(uuid4()),
        "layer2_run_id":    str(row["run_id"]),
        "sequential_run_id": str(row.get("sequential_run_id", "")),
        "business_id":      str(row["business_id"]),
        "date":             str(row["date"]),
        "archetype":        row["archetype"],

        # N10 construye este campo como primer paso del grafo
        "enriched_payload": {},

        # Borrador — None hasta que N11 lo genere
        "draft_report": None,

        # Control del loop — valores iniciales
        "intentos_critico":    0,
        "feedback_critico":    None,
        "historial_feedback":  [],
        "tipos_falla_critico": [],
        "draft_status":        "pending",
        "audit_results":       [],
    }
```

---

## Invocación del Grafo

```python
# En api/main.py — startup
from agents.layer3_graph import build_layer3_graph
from utils.memory_service import MemoryService

# MemoryService instanciado una vez al arrancar el servidor
memory_service = MemoryService(supabase_client=supabase)
layer3_app = build_layer3_graph(memory_service)

# En el endpoint POST /api/audit/layer3/run
@app.post("/api/audit/layer3/run", status_code=202)
async def run_layer3(payload: Layer3RunPayload, background_tasks: BackgroundTasks):
    initial_state = await build_initial_state(payload.audit_run_id, db)

    # El grafo corre en background — el endpoint responde 202 inmediatamente
    background_tasks.add_task(layer3_app.ainvoke, initial_state)

    return {
        "layer3_run_id": initial_state["layer3_run_id"],
        "audit_run_id":  payload.audit_run_id,
        "status":        "running",
        "started_at":    datetime.now(timezone.utc).isoformat(),
    }
```

---

## Acceptance Criteria

- WHEN `audit_run_id` válido → endpoint responde 202 e inicia el grafo en background
- WHEN mismo `audit_run_id` enviado dos veces → HTTP 409, no re-ejecutar el grafo
- WHEN `audit_run_id` no existe → HTTP 404 antes de invocar el grafo
- WHEN grafo completa → `GET /status` retorna `status: "completed"` con `draft_status`
- WHEN grafo falla → `GET /status` retorna `status: "failed"` con `error_detail`
- WHEN `GET /result` antes de completar → HTTP 409
- WHEN `layer3_app` importado en `api/main.py` → no hay `StateGraph` instanciado en ese archivo

---

## Archivos relacionados
- `agents/layer3_graph.py` — grafo compilado `layer3_app`
- `agents/layer3_state.py` — `Layer3State` TypedDict
- `layer3_graph.md` — arquitectura del grafo
- `n14_informe_final.md` — nodo terminal que produce el `FinalReport`
