# MEPIA — Arquitectura de Base de Datos

**Tipo:** Híbrida — campos estructurados para cálculos financieros + JSONB para datos flexibles
**Motor:** PostgreSQL via Supabase
**Migración:** `supabase/migrations/002_hybrid_schema.sql`

---

## Tabla: `businesses`

Entidad raíz. Todo dato financiero está ligado a un negocio.

| Campo      | Tipo    | Notas                              |
|------------|---------|------------------------------------|
| id         | uuid PK | gen_random_uuid()                  |
| name       | text    | Nombre del restaurante             |
| sector     | text    | ej. "restaurante", "cafetería"     |
| currency   | text    | ISO 4217, default "MXN"            |
| created_at | timestamptz | default now()                  |

---

## Tabla: `documents`

Gestiona archivos subidos (PDFs, XMLs, imágenes). Punto de entrada del pipeline.

| Campo          | Tipo    | Notas                                          |
|----------------|---------|------------------------------------------------|
| id             | uuid PK | = file_id del POSIngestResult                  |
| business_id    | uuid FK | → businesses.id                                |
| storage_path   | text    | Ruta en Supabase Storage                       |
| filename       | text    | Nombre original del archivo                    |
| document_type  | text    | "PDF" \| "XML" \| "JPG"                        |
| ocr_status     | text    | "pending" \| "processed" \| "error"            |
| uploaded_at    | timestamptz | default now()                              |
| extracted_data | jsonb   | Respuesta cruda del agente IA antes de normalizar a transactions |

**`extracted_data` — ejemplos de contenido:**
```json
// Ticket POS
{ "business_name": "Café Roma", "period": "2026-04-22",
  "totals": { "total_ventas": 5150.00, "numero_transacciones": 47 },
  "extraction_status": "success" }

// Factura proveedor
{ "proveedor": "Lácteos del Norte", "serie": "A-00123",
  "dias_credito": 30, "subtotal": 4200.00, "iva": 672.00 }
```

---

## Tabla: `transactions`

Datos financieros normalizados. Campos fijos para cálculos + JSONB para variaciones por tipo de documento.

| Campo            | Tipo         | Notas                                              |
|------------------|--------------|----------------------------------------------------|
| id               | uuid PK      | gen_random_uuid()                                  |
| business_id      | uuid FK      | → businesses.id (NOT NULL)                         |
| document_id      | uuid FK      | → documents.id (trazabilidad al archivo origen)    |
| type             | text         | "ingreso" \| "egreso"                              |
| category         | text         | "venta" \| "nomina" \| "proveedor" \| "impuesto"   |
| amount           | numeric(12,2)| Siempre positivo; type define la dirección         |
| transaction_date | date         | Fecha del evento financiero                        |
| created_at       | timestamptz  | default now()                                      |
| metadata         | jsonb        | Datos extra que varían por tipo de documento       |

**`metadata` — ejemplos por categoría:**
```json
// category = "venta" (ticket POS)
{ "metodo_pago": "efectivo", "cajero_id": "C-04", "turno": "matutino" }

// category = "proveedor" (factura)
{ "serie_factura": "A-00123", "dias_credito": 30, "proveedor": "Lácteos del Norte" }

// category = "nomina"
{ "empleado_id": "E-12", "periodo": "quincenal", "concepto": "sueldo base" }
```

---

## Índices y restricciones

```sql
-- Búsquedas rápidas por campos dinámicos en metadata
CREATE INDEX idx_transactions_metadata ON transactions USING GIN (metadata);

-- Búsquedas en extracted_data de documentos
CREATE INDEX idx_documents_extracted ON documents USING GIN (extracted_data);

-- Consultas frecuentes por negocio + fecha
CREATE INDEX idx_transactions_business_date ON transactions (business_id, transaction_date);

-- Filtrar documentos por estado OCR
CREATE INDEX idx_documents_ocr_status ON documents (ocr_status);
```

---

## Relaciones

```
businesses (1) ──< documents (N)
businesses (1) ──< transactions (N)
documents  (1) ──< transactions (N)
```

---

## Tabla: `unit_conversions`

Catálogo de conversiones de unidades para el Motor de Cálculo.

| Campo         | Tipo    | Notas                          |
|---------------|---------|--------------------------------|
| id            | uuid PK | gen_random_uuid()              |
| from_unit     | text    | ej. "kg"                       |
| to_unit       | text    | ej. "g" (unidad base)          |
| factor        | decimal | ej. 1000                       |

Registros iniciales: `kg→g (×1000)`, `L→ml (×1000)`, `unidad→unidad (×1)`

---

## Tabla: `recipes` (BOM — Bill of Materials)

Define la receta técnica de cada producto. Base para calcular mermas y costo teórico.

| Campo        | Tipo    | Notas                                      |
|--------------|---------|--------------------------------------------|
| id           | uuid PK | gen_random_uuid()                          |
| business_id  | uuid FK | → businesses.id                            |
| product_name | text    | ej. "Café Latte"                           |
| ingredients  | jsonb   | `{ "cafe_g": 18, "leche_ml": 250 }`        |
| updated_at   | timestamptz | default now()                          |

---

## Tabla: `daily_context`

Contexto del día capturado via Tags Rápidos al cierre de carga.

| Campo       | Tipo    | Notas                                           |
|-------------|---------|-------------------------------------------------|
| id          | uuid PK | gen_random_uuid()                               |
| business_id | uuid FK | → businesses.id                                 |
| date        | date    | Fecha del contexto                              |
| tags        | jsonb   | `{ "clima": "lluvia", "equipo": "falla_maquina", "evento": null, "personal": null, "otros": "texto libre" }` |
| created_at  | timestamptz | default now()                               |

---

## Tabla: `metric_status`

Estado de cada métrica por negocio y fecha. Gestionado por el Gatekeeper (S2).

| Campo          | Tipo    | Notas                                       |
|----------------|---------|---------------------------------------------|
| id             | uuid PK | gen_random_uuid()                           |
| business_id    | uuid FK | → businesses.id                             |
| date           | date    | Fecha de evaluación                         |
| metric_name    | text    | ej. "merma", "margen_utilidad"              |
| status         | text    | "dormant" \| "active"                       |
| missing_fields | jsonb   | `["compras_insumos", "recipe"]` o `[]`      |
| updated_at     | timestamptz | default now()                           |

---

## Índices adicionales

```sql
CREATE INDEX idx_daily_context_business_date ON daily_context (business_id, date);
CREATE INDEX idx_metric_status_lookup ON metric_status (business_id, date, status);
CREATE INDEX idx_recipes_business ON recipes (business_id);
```

---

## Notas de migración

- La tabla `transactions` original (`001_init.sql`) queda deprecada → reemplazada por schema híbrido
- La tabla `audit_results` original se mantiene sin cambios (outputs de agentes)
- El campo `raw_json` de la tabla original equivale a `metadata` en el nuevo schema
- Nuevas tablas: `recipes`, `daily_context`, `metric_status`
