# S1 — Ingesta (The 5 Inputs)

**Capa:** Sequential | **Siguiente nodo:** S2 Gatekeeper
**Archivos relacionados:** `app/api/upload/route.ts`, `api/main.py`, `db_schema.md`

## Los 5 inputs

| # | Fuente              | Mecanismo           | Destino DB                        |
|---|---------------------|---------------------|-----------------------------------|
| 1 | POS / PDF           | OCR + mapeo         | `documents` + `transactions`      |
| 2 | Facturas proveedor  | OCR + mapeo         | `documents` + `transactions`      |
| 3 | Recetas (BOM)       | Formulario manual   | `recipes`                         |
| 4 | Config inicial      | Onboarding          | `businesses`                      |
| 5 | Contexto del día    | Tags rápidos + texto| `daily_context.tags` (JSONB)      |

## Input 5 — Formulario de Contexto (Tags Rápidos)

Componente presentado al cierre de cada carga o fin de día. Opciones cerradas para minimizar fricción.

```
Clima:    [Lluvia] [Calor] [Frío]
Equipo:   [Falla de Máquina] [Mantenimiento]
Evento:   [Festivo] [Obra Vial] [Promoción]
Personal: [Falta de Staff] [Capacitación]
Otros:    [campo de texto libre]
```

Se guarda en `daily_context.tags` (JSONB):
```json
{
  "clima": "lluvia",
  "equipo": "falla_maquina",
  "evento": null,
  "personal": null,
  "otros": "La máquina de espresso estuvo fuera 3 horas"
}
```

## Input 3 — Receta Técnica (BOM)

Define el costo teórico de cada producto. Base para calcular mermas.

```
Café Latte = { cafe_g: 18, leche_ml: 250, vaso: 1 }
```

Se guarda en tabla `recipes`: `product_name`, `business_id`, `ingredients` (JSONB).

## Output de S1

`POSIngestResult`:
```
file_id: UUID → documents.id
storage_path: string → documents.storage_path
extraction_status: "success" | "fallback_required" → documents.ocr_status
extracted_data: JSONB → documents.extracted_data
context_tag_id: UUID → daily_context.id
```

## Acceptance Criteria

- WHEN PDF válido → persistir en Storage + insertar en `documents` con `ocr_status: "pending"`
- WHEN OCR completa → actualizar `ocr_status: "processed"` + poblar `extracted_data`
- WHEN OCR falla → `ocr_status: "error"` + mostrar formulario manual
- WHEN usuario envía tags → insertar en `daily_context` con `business_id` + `date`
- WHEN campo "Otros" vacío → guardar `null`, no string vacío
- WHEN receta guardada → validar que `ingredients` tenga al menos 1 campo no nulo

## Edge Cases

- PDF con contraseña → `ocr_status: "error"` + mensaje al usuario
- Tags enviados sin PDF del día → aceptar y asociar a `date` actual
- Receta duplicada para mismo producto → sobrescribir, no duplicar
