# S1 — Ingesta (3 Inputs)

**Capa:** Sequential | **Siguiente nodo:** S2 Gatekeeper
**Archivos relacionados:** `api/main.py`, `db_schema.md`, `n01_pos_pdf_input.md`, `n02_facturas_input.md`, `n03_human_input_endpoints.md`, `s1b_ingesta_api.md`
**Enfoque:** API-First / Headless — sin dependencias de UI

## Los 3 inputs

| # | Fuente              | Mecanismo                  | Destino DB                          |
|---|---------------------|----------------------------|-------------------------------------|
| 1 | POS / API (primaria) + PDF (fallback) | JSON estructurado / OCR + mapeo Pydantic | `documents` + `transactions` + tablas extendidas |
| 2 | Facturas proveedor  | XML determinístico / OCR   | `documents` + `transactions`        |
| 3 | Recetas (BOM)       | Formulario manual          | `recipes`                           |

> **Nota:** "Contexto del día" (daily_context, tags + texto libre) fue retirado del pipeline. No aporta al diseño final y generaba ruido. La tabla `daily_context` queda deprecated — ver `db_schema.md`.
> **Nota:** Config inicial (Onboarding) no es un input de ingesta recurrente — es un prerequisito de setup. Ver `n10_onboarding_identidad.md`.

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
needs_human_review: bool
```

## Acceptance Criteria

- WHEN OCR confianza < 85% → `needs_human_review: true`, no pasar a S2
- WHEN OCR confianza ≥ 85% → mapear campos obligatorios, resto a `raw_metadata`
- WHEN campo obligatorio ausente en factura → `needs_human_review: true`
- WHEN receta guardada → validar ≥ 1 ingrediente no nulo
- WHEN onboarding completo → `businesses` + al menos 1 registro en `business_fixed_costs`
