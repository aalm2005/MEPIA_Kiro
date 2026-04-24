# N01 — POS PDF Input

**Capa:** Sequential | **Parte de:** S1 Ingesta | **Siguiente nodo:** S2 Gatekeeper
**Archivos relacionados:** `api/main.py`, `db_schema.md`
**Enfoque:** API-First / Headless — sin dependencias de UI

## Input / Output

- **Input:** Archivo PDF vía `multipart/form-data` — cualquier cliente HTTP
- **Output:** `POSIngestResult` → ver contrato en `_glossary.md`

## Endpoint

### `POST /ingest/pos`

**Request:** `multipart/form-data`

| Campo         | Tipo   | Requerido | Descripción                        |
|---------------|--------|-----------|------------------------------------|
| `file`        | File   | ✅        | Archivo PDF del ticket POS         |
| `business_id` | UUID   | ✅        | Negocio al que pertenece el ticket |

**Response 200 — extracción exitosa:**
```json
{
  "file_id": "uuid-v4",
  "storage_path": "pos-tickets/{business_id}/{date}/{file_id}.pdf",
  "extraction_status": "success",
  "needs_human_review": false,
  "uploaded_at": "2024-01-15T22:00:00Z",
  "extracted_data": {
    "business_name": "Café Mepia",
    "period": "2024-01-15",
    "totals": { "cash": 3200.00, "card": 1950.00, "total": 5150.00 }
  }
}
```

**Response 200 — fallback requerido:**
```json
{
  "file_id": "uuid-v4",
  "storage_path": "pos-tickets/{business_id}/{date}/{file_id}.pdf",
  "extraction_status": "fallback_required",
  "needs_human_review": false,
  "uploaded_at": "2024-01-15T22:00:00Z",
  "extracted_data": null
}
```

**Códigos de error:**

| HTTP | Condición                                      |
|------|------------------------------------------------|
| 422  | MIME ≠ `application/pdf`                       |
| 413  | Archivo > 20 MB                                |
| 422  | Archivo vacío (0 bytes)                        |
| 422  | PDF corrupto o con contraseña                  |
| 404  | `business_id` no existe                        |
| 503  | Storage de Supabase no disponible              |

---

### `PATCH /ingest/pos/{file_id}/metadata`

Envía los datos del ticket manualmente cuando `extraction_status: "fallback_required"`.
Cable suelto para la futura UI o cualquier cliente que quiera resolver el fallback.

**Request body — `POSMetadataPayload`:**

```python
class POSTotals(BaseModel):
    cash: Decimal = Field(ge=0, decimal_places=2)
    card: Decimal = Field(ge=0, decimal_places=2)
    total: Decimal = Field(gt=0, decimal_places=2)

class POSMetadataPayload(BaseModel):
    business_name: str = Field(min_length=1, max_length=255)
    period: date                                    # ISO-8601 YYYY-MM-DD
    totals: POSTotals
```

**Response 200:**
```json
{
  "file_id": "uuid-v4",
  "extraction_status": "success",
  "needs_human_review": false
}
```

**Códigos de error:**

| HTTP | Condición                                                    |
|------|--------------------------------------------------------------|
| 404  | `file_id` no existe                                          |
| 409  | Documento ya tiene `extraction_status: "success"`            |
| 422  | Validación Pydantic fallida                                  |

## Persistencia

| Campo del resultado     | Se guarda en                  |
|-------------------------|-------------------------------|
| `file_id`               | `documents.id`                |
| `storage_path`          | `documents.storage_path`      |
| `extracted_data` (crudo)| `documents.extracted_data`    |
| `ocr_status`            | `documents.ocr_status`        |
| `business_name`, `period`, `totals` | `pos_inputs` (tras normalización) |

## Acceptance Criteria

**Subida y persistencia**
- WHEN PDF válido recibido → persistir en Storage `pos-tickets/{business_id}/{date}/{file_id}.pdf`
- WHEN persistido → retornar `POSIngestResult` con `file_id` (UUID v4), `storage_path`, `uploaded_at` (UTC ISO-8601)

**Validación**
- WHEN MIME ≠ `application/pdf` → HTTP 422
- WHEN tamaño > 20 MB → HTTP 413
- WHEN 0 bytes → HTTP 422
- WHEN PDF corrupto → HTTP 422 (sin excepción no manejada)
- WHEN Storage caído → HTTP 503 + log con stack trace

**Extracción automática**
- WHEN tablas reconocibles → extraer `business_name`, `period`, `totals`; `extraction_status: "success"`
- WHEN extracción parcial → poblar campos extraídos, `null` solo en los fallidos
- WHEN sin tablas / imagen escaneada → `extraction_status: "fallback_required"`, `extracted_data: null`

**Fallback manual vía API**
- WHEN `fallback_required` → cliente llama `PATCH /ingest/pos/{file_id}/metadata` con datos manuales
- WHEN metadata manual recibida para `file_id` existente → actualizar registro, `extraction_status: "success"`
- WHEN `period` en formato incorrecto → HTTP 422

**Deduplicación**
- WHEN mismo SHA-256 + mismo `business_id` subido N veces → retornar POSIngestResult original, sin duplicar en Storage

## Correctness Properties (PBT)

| ID | Propiedad |
|----|-----------|
| P1 | `file_id`, `filename`, `uploaded_at`, `storage_path`, `extraction_status` siempre no nulos en todo POSIngestResult |
| P2 | `deserialize(serialize(result)) == result` (round-trip JSON) |
| P3 | Mismo SHA-256 + `business_id` → exactamente 1 objeto en Storage |
| P4 | Archivo inválido → HTTP 4xx + `errors` con al menos 1 mensaje |
| P5 | Extracción parcial → campos extraídos no nulos, solo los fallidos en `null` |
| P6 | `fallback_required` automático → `business_name`, `period`, `totals` todos `null` |

## Edge Cases

- PDF con contraseña → tratar como corrupto (HTTP 422)
- PDF de múltiples páginas → extraer de primera página con tablas
- Timeout de Storage > 30s → HTTP 503
- `totals` con valores negativos → aceptar y registrar warning
