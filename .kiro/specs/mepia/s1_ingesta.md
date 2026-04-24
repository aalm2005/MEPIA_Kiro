# S1 — Ingesta (The 5 Inputs)

**Capa:** Sequential | **Siguiente nodo:** S2 Gatekeeper
**Archivos relacionados:** `api/main.py`, `db_schema.md`, `n01_pos_pdf_input.md`, `n02_facturas_input.md`, `n03_human_input_endpoints.md`
**Enfoque:** API-First / Headless — sin dependencias de UI

## Los 5 inputs

| # | Fuente              | Mecanismo                  | Destino DB                          |
|---|---------------------|----------------------------|-------------------------------------|
| 1 | POS / PDF           | OCR + mapeo Pydantic       | `documents` + `transactions`        |
| 2 | Facturas proveedor  | XML determinístico / OCR   | `documents` + `transactions`        |
| 3 | Recetas (BOM)       | Formulario manual          | `recipes`                           |
| 4 | Config inicial      | Onboarding                 | `businesses` + `business_fixed_costs`|
| 5 | Contexto del día    | Tags rápidos + texto libre | `daily_context.tags` (JSONB)        |

---

## Input 2 — Facturas de Proveedor

Detalle completo del contrato de API en `n02_facturas_input.md`.

Resumen del flujo:
- XML: parseo determinístico (lxml) → confianza 100%, sin OCR
- PDF: modelo visión/OCR → umbral 85%
- Endpoint: `POST /ingest/factura`
- Revisión humana: `PATCH /ingest/factura/{file_id}/review` (ver `n02_facturas_input.md`)
- `expense_behavior` siempre sale como `null` de este paso — se confirma vía `n03_human_input_endpoints.md`

---

## Input 4 — Configuración Inicial (Onboarding)

Contrato de API completo en `n03_human_input_endpoints.md` → `POST /onboarding/business`.

Resumen: operación atómica que crea `businesses` + mínimo 1 `business_fixed_costs`. Rollback total si falla cualquier gasto fijo.

## Input 5 — Contexto del Día (Tags)

Contrato de API en `n03_human_input_endpoints.md` → `POST /daily-context`.

Estructura del JSONB guardado en `daily_context.tags`:
```json
{ "clima": "lluvia", "equipo": "falla_maquina", "evento": null, "personal": null, "otros": "..." }
```
Regla: `null` en campos vacíos, nunca string vacío.

---

## Input 3 — Receta Técnica (BOM)

```
Café Latte = { cafe_g: 18, leche_ml: 250, vaso: 1 }
```
Guardado en `recipes.ingredients` (JSONB). Receta duplicada → sobrescribir.

---

## Output de S1

```
file_id: UUID → documents.id
storage_path: string
extraction_status: "success" | "fallback_required" | "needs_human_review"
extracted_data: JSONB → documents.extracted_data
context_tag_id: UUID → daily_context.id
needs_human_review: bool
```

## Acceptance Criteria

- WHEN OCR confianza < 85% → `needs_human_review: true`, no pasar a S2
- WHEN OCR confianza ≥ 85% → mapear campos obligatorios, resto a `raw_metadata`
- WHEN campo obligatorio ausente en factura → `needs_human_review: true`
- WHEN receta guardada → validar ≥ 1 ingrediente no nulo
- WHEN tags enviados → `null` en campos vacíos, nunca string vacío
- WHEN onboarding completo → `businesses` + al menos 1 registro en `business_fixed_costs`
