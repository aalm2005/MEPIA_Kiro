# N02 — Facturas de Proveedor Input

**Capa:** Sequential | **Parte de:** S1 Ingesta | **Siguiente nodo:** S2 Gatekeeper
**Archivos relacionados:** `api/main.py`, `db_schema.md`
**Enfoque:** API-First / Headless — sin dependencias de UI

---

## Responsabilidad

Recibir facturas de proveedor en formato XML (CFDI) o PDF, extraer los campos obligatorios,
persistir en `documents` + `transactions`, y exponer endpoints REST para que cualquier cliente
(UI, script, integración) consuma el flujo.

---

## Formatos soportados

| Formato | Mecanismo de extracción          | Confianza esperada |
|---------|----------------------------------|--------------------|
| XML     | Parseo determinístico (lxml)     | 100% — sin OCR     |
| PDF     | Modelo visión / OCR (pdfplumber) | Variable — umbral 85% |

---

## Endpoints REST

### `POST /ingest/factura`

Recibe el archivo de factura (XML o PDF) y dispara el pipeline de extracción.

**Request:** `multipart/form-data`

| Campo         | Tipo   | Requerido | Descripción                              |
|---------------|--------|-----------|------------------------------------------|
| `file`        | File   | ✅        | Archivo XML o PDF de la factura          |
| `business_id` | UUID   | ✅        | Negocio al que pertenece la factura      |
| `document_type` | string | ✅      | `"XML"` \| `"PDF"`                       |

**Response 200 — extracción exitosa:**
```json
{
  "file_id": "uuid-v4",
  "storage_path": "facturas/{business_id}/{date}/{file_id}.xml",
  "extraction_status": "success",
  "needs_human_review": false,
  "transaction_id": "uuid-v4",
  "extracted_fields": {
    "transaction_date": "2024-01-15",
    "amount": 1160.00,
    "tax_amount": 160.00,
    "supplier_name": "Distribuidora La Paloma SA",
    "concept": "Leche entera 24 piezas",
    "document_reference": "FAC-2024-00123"
  }
}
```

**Response 200 — requiere revisión humana:**
```json
{
  "file_id": "uuid-v4",
  "storage_path": "facturas/{business_id}/{date}/{file_id}.pdf",
  "extraction_status": "needs_human_review",
  "needs_human_review": true,
  "ocr_confidence": 72.4,
  "transaction_id": null,
  "extracted_fields": null,
  "missing_fields": ["supplier_name", "document_reference"]
}
```

**Códigos de error:**

| HTTP | Condición                                      |
|------|------------------------------------------------|
| 422  | MIME no soportado (no es XML ni PDF)           |
| 422  | `document_type` no coincide con MIME real      |
| 413  | Archivo > 20 MB                                |
| 422  | Archivo vacío (0 bytes)                        |
| 422  | PDF corrupto o con contraseña                  |
| 422  | XML inválido / no es CFDI                      |
| 404  | `business_id` no existe en `businesses`        |
| 503  | Storage de Supabase no disponible              |

---

### `PATCH /ingest/factura/{file_id}/review`

Permite a un cliente externo enviar los campos corregidos cuando `needs_human_review: true`.
Este es el "cable suelto" para la futura UI de revisión.

**Request body:** `application/json`

```json
{
  "transaction_date": "2024-01-15",
  "amount": 1160.00,
  "tax_amount": 160.00,
  "supplier_name": "Distribuidora La Paloma SA",
  "concept": "Leche entera 24 piezas",
  "document_reference": "FAC-2024-00123"
}
```

**Modelo Pydantic — `FacturaReviewPayload`:**

```python
class FacturaReviewPayload(BaseModel):
    transaction_date: date                          # formato ISO-8601 YYYY-MM-DD
    amount: Decimal = Field(gt=0, decimal_places=2)
    tax_amount: Decimal = Field(ge=0, decimal_places=2)
    supplier_name: str = Field(min_length=1, max_length=255)
    concept: str = Field(min_length=1, max_length=500)
    document_reference: str = Field(min_length=1, max_length=100)
```

**Response 200:**
```json
{
  "file_id": "uuid-v4",
  "transaction_id": "uuid-v4",
  "extraction_status": "success",
  "needs_human_review": false
}
```

**Códigos de error:**

| HTTP | Condición                                              |
|------|--------------------------------------------------------|
| 404  | `file_id` no existe                                    |
| 409  | Documento ya tiene `extraction_status: "success"`      |
| 422  | Validación Pydantic fallida (campo inválido o ausente) |

---

## Mapeo de extracción → `transactions`

| Campo extraído         | Columna en `transactions`  | Fuente XML (CFDI)              |
|------------------------|----------------------------|--------------------------------|
| Fecha                  | `transaction_date`         | `@Fecha` en `cfdi:Comprobante` |
| Total                  | `amount`                   | `@Total`                       |
| IVA                    | `tax_amount`               | `cfdi:Impuestos/@TotalImpuestosTrasladados` |
| Nombre proveedor       | `supplier_name`            | `cfdi:Emisor/@Nombre`          |
| Concepto / partidas    | `concept`                  | `cfdi:Conceptos/cfdi:Concepto/@Descripcion` |
| Folio / referencia     | `document_reference`       | `@Folio` o `@NoCertificado`    |

Todo campo XML fuera de este mapeo → `transactions.raw_metadata` (JSONB). No se descarta nada.

---

## Flujo interno del pipeline

```
POST /ingest/factura
  │
  ├─ Validar MIME + tamaño + business_id
  ├─ Persistir archivo en Supabase Storage
  ├─ Crear registro en documents (ocr_status: "pending")
  │
  ├─ [XML] → parseo determinístico lxml
  │     └─ Extraer campos obligatorios
  │     └─ ocr_confidence = 100, needs_human_review = false
  │
  ├─ [PDF] → OCR / modelo visión
  │     ├─ confianza ≥ 85% → extraer campos, needs_human_review = false
  │     └─ confianza < 85% → needs_human_review = true, DETENER hacia S2
  │
  ├─ Validar campos obligatorios presentes
  │     └─ campo ausente → needs_human_review = true
  │
  ├─ Inferir category_id por supplier_name o concept
  ├─ Insertar en transactions (expense_behavior = null — pendiente confirmación)
  └─ Actualizar documents (ocr_status: "processed" | "error")
```

**Nota:** `expense_behavior` se persiste como `null` en este paso. La confirmación se realiza
vía endpoint dedicado (ver spec de `expense_behavior` endpoints).

---

## Deduplicación

- Mismo SHA-256 + mismo `business_id` → retornar el `FacturaIngestResult` original sin duplicar en Storage ni en `transactions`.

---

## Modelo Pydantic de respuesta — `FacturaIngestResult`

```python
class ExtractedFacturaFields(BaseModel):
    transaction_date: date
    amount: Decimal
    tax_amount: Decimal
    supplier_name: str
    concept: str
    document_reference: str

class FacturaIngestResult(BaseModel):
    file_id: UUID
    storage_path: str
    extraction_status: Literal["success", "needs_human_review"]
    needs_human_review: bool
    ocr_confidence: Optional[float]       # None para XML
    transaction_id: Optional[UUID]        # None si needs_human_review
    extracted_fields: Optional[ExtractedFacturaFields]
    missing_fields: Optional[list[str]]   # campos que fallaron en extracción parcial
```

---

## Acceptance Criteria

- WHEN XML válido (CFDI) → `extraction_status: "success"`, `ocr_confidence: null`, todos los campos obligatorios mapeados
- WHEN PDF con confianza ≥ 85% → `extraction_status: "success"`, `transaction_id` no nulo
- WHEN PDF con confianza < 85% → `extraction_status: "needs_human_review"`, `transaction_id: null`, no pasar a S2
- WHEN campo obligatorio ausente (cualquier formato) → `needs_human_review: true`
- WHEN `PATCH /review` recibido → actualizar `documents` + crear `transactions`, `extraction_status: "success"`
- WHEN mismo SHA-256 + `business_id` → retornar resultado original, sin duplicados
- WHEN XML no es CFDI válido → HTTP 422
- WHEN `business_id` no existe → HTTP 404
- WHEN `expense_behavior` → siempre `null` al salir de N02, nunca asumir

---

## Correctness Properties (PBT)

| ID | Propiedad |
|----|-----------|
| P1 | `file_id`, `storage_path`, `extraction_status`, `needs_human_review` siempre no nulos en todo `FacturaIngestResult` |
| P2 | `deserialize(serialize(result)) == result` (round-trip JSON) |
| P3 | Mismo SHA-256 + `business_id` → exactamente 1 objeto en Storage y 1 en `documents` |
| P4 | Archivo inválido → HTTP 4xx + mensaje de error descriptivo |
| P5 | XML CFDI válido → `ocr_confidence` es `null` y `extraction_status: "success"` |
| P6 | `needs_human_review: true` → `transaction_id` es `null` y `expense_behavior` no existe en `transactions` |
| P7 | `PATCH /review` exitoso → `needs_human_review` cambia a `false` y `transaction_id` no nulo |

---

## Edge Cases

- XML con múltiples conceptos → concatenar descripciones en `concept`, guardar array completo en `raw_metadata`
- PDF de múltiples páginas → extraer de la página con mayor densidad de datos tabulares
- Factura con `amount` = 0 → HTTP 422 (monto inválido)
- Timeout de Storage > 30s → HTTP 503
- `tax_amount` > `amount` → HTTP 422 (inconsistencia de datos)
