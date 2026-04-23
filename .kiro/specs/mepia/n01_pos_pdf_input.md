# N01 — POS PDF Input

**Capa:** Sequential | **Siguiente nodo:** N02 Parser Agent
**Archivos relacionados:** `app/api/upload/route.ts`, `api/main.py`

## Input / Output

- **Input:** Archivo PDF del browser (multipart/form-data)
- **Output:** `POSIngestResult` → ver contrato en `_glossary.md`

## Persistencia

| Campo del resultado   | Se guarda en              |
|-----------------------|---------------------------|
| file_id               | `documents.id`            |
| storage_path          | `documents.storage_path`  |
| extracted_data (crudo)| `documents.extracted_data`|
| ocr_status            | `documents.ocr_status`    |
| business_name, period, totals | `transactions.metadata` (tras normalización en N02) |

## User Stories

**US-1:** Como dueño de restaurante, subo mi ticket diario en PDF para iniciar la auditoría.
**US-2:** Como dueño, quiero que el sistema extraiga automáticamente nombre, período y totales del PDF.
**US-3:** Como dueño, si la extracción falla, quiero ingresar los datos manualmente para no bloquear la auditoría.
**US-4:** Como dueño, quiero que el sistema rechace archivos inválidos con un mensaje claro.

## Acceptance Criteria

**Subida y persistencia**
- WHEN PDF válido recibido → persistir en Storage `pos-tickets/{user_id}/{date}/{file_id}.pdf`
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
- WHEN sin tablas / imagen escaneada → `extraction_status: "fallback_required"`, metadata en `null`

**Fallback manual**
- WHEN `fallback_required` → frontend muestra formulario; usuario envía metadata manualmente
- WHEN metadata manual recibida para `file_id` existente → actualizar registro, `extraction_status: "success"`
- WHEN `period` en formato incorrecto en formulario → HTTP 422

**Deduplicación**
- WHEN mismo SHA-256 + mismo `user_id` subido N veces → retornar POSIngestResult original, sin duplicar en Storage

## Correctness Properties (PBT)

| ID | Propiedad |
|----|-----------|
| P1 | `file_id`, `filename`, `uploaded_at`, `storage_path`, `extraction_status` siempre no nulos en todo POSIngestResult |
| P2 | `deserialize(serialize(result)) == result` (round-trip JSON) |
| P3 | Mismo SHA-256 + user_id → exactamente 1 objeto en Storage |
| P4 | Archivo inválido → HTTP 4xx + `errors` con al menos 1 mensaje |
| P5 | Extracción parcial → campos extraídos no nulos, solo los fallidos en `null` |
| P6 | `fallback_required` automático → `business_name`, `period`, `totals` todos `null` |

## Edge Cases

- PDF con contraseña → tratar como corrupto (HTTP 422)
- PDF de múltiples páginas → extraer de primera página con tablas
- Timeout de Storage > 30s → HTTP 503
- `totals` con valores negativos → aceptar y registrar warning
