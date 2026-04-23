# MEPIA — Glosario Compartido

## Términos del dominio

| Término            | Definición |
|--------------------|------------|
| POS_PDF            | Reporte diario de ventas del sistema de punto de venta, en formato PDF |
| Ticket diario      | Sinónimo de POS_PDF |
| Metadata           | `business_name`, `period`, `totals` extraídos del POS_PDF |
| SharedHeader       | Subconjunto de Metadata que se pasa a todos los agentes paralelos: `business_name`, `period`, `totals` |
| CEO Archetype      | Perfil del dueño: `Operative Genius` \| `Product Purist` \| `Growth Hacker` |
| CEO Cognitive Frame| Lente + blind spots + question set inyectado en el system prompt de cada agente |
| Q-Framework        | 5 preguntas del Auditor Agent: constraint, margin leak, ignored data, 3x scale, bottleneck |
| AgentResult        | Output estándar de todo agente: `module`, `raw_result`, `copilot_phrase`, `archetype` |
| Warning            | Señal de anomalía generada por un agente paralelo, recolectada para el Loop/Critic |
| Informe Final      | Output terminal del sistema: expandido, validado, CEO-framed |

## Componentes de infraestructura

| Componente         | Tecnología       | Responsabilidad |
|--------------------|------------------|-----------------|
| Upload_Handler     | Next.js API Route| Recibe archivo del browser, proxy a FastAPI |
| Ingest_Service     | FastAPI `/ingest`| Valida, persiste, parsea POS_PDF |
| Storage            | Supabase Storage | Persiste PDFs en `pos-tickets/{user_id}/{date}/{file_id}.pdf` |
| mepia.db           | SQLite           | Memoria estructurada: audit_runs, daily_metrics, ceo_insights, warnings_log |
| Memory_Writer      | Python module    | Escribe JSON en mepia.db tras el Sequential pipeline |
| Memory_Reader      | Python module    | Lee últimos N días + deltas para el Auditor Agent |
| RAG_KB             | Vector store     | Entrevistas de auditores + NIIF, consultado por Consultor Especialista |

## Base de datos — Tablas principales

| Tabla            | Propósito |
|------------------|-----------|
| `businesses`     | Entidad raíz. Todo dato financiero está ligado a un negocio |
| `documents`      | Archivos subidos. `extracted_data` (JSONB) = respuesta cruda del agente IA |
| `transactions`   | Datos financieros normalizados. `metadata` (JSONB) = variaciones por tipo |
| `recipes`        | Receta técnica (BOM) por producto. Base para cálculo de mermas |
| `daily_context`  | Tags de contexto del día (clima, equipo, evento, personal, otros) |
| `metric_status`  | Estado `dormant`/`active` por métrica, negocio y fecha (Gatekeeper S2) |
| `audit_results`  | Outputs de agentes: `module`, `raw_result`, `copilot_phrase`, `archetype` |

## Campos JSONB clave

| Campo              | Tabla           | Contenido |
|--------------------|-----------------|-----------|
| `extracted_data`   | `documents`     | Respuesta cruda del agente IA antes de normalizar |
| `metadata`         | `transactions`  | Datos extra por tipo: método de pago, cajero, serie factura, etc. |
| `tags`             | `daily_context` | `{ clima, equipo, evento, personal, otros }` |
| `ingredients`      | `recipes`       | `{ cafe_g: 18, leche_ml: 250 }` |
| `missing_fields`   | `metric_status` | Lista de datos faltantes para activar la métrica |

## Estados de métricas (Gatekeeper)

| Estado           | Significado                                      |
|------------------|--------------------------------------------------|
| `dormant`        | Faltan datos requeridos. No se calcula en S3.    |
| `active`         | Set de datos completo. Pasa al Motor de Cálculo. |

## Status de CalcResult

| Status            | Significado                                              |
|-------------------|----------------------------------------------------------|
| `ok`              | Cálculo exitoso, dentro de umbrales normales             |
| `warning`         | Cálculo exitoso, valor en zona de atención               |
| `critical`        | Cálculo exitoso, valor fuera de umbral crítico           |
| `incomplete_data` | Faltan datos o división por cero — no se calculó         |
| `unit_mismatch`   | Unidades incompatibles entre receta y factura            |

## Normalización de unidades (Motor de Cálculo)

| Unidad origen | Unidad base | Factor |
|---------------|-------------|--------|
| kg            | g           | × 1000 |
| L             | ml          | × 1000 |
| unidad        | unidad      | × 1    |

## Contratos de datos

### POSIngestResult
```
file_id: UUID v4                          → documents.id
filename: string                          → documents.filename
uploaded_at: ISO-8601 UTC                 → documents.uploaded_at
storage_path: string                      → documents.storage_path
business_name: string | null              → documents.extracted_data.business_name
period: "YYYY-MM-DD" | "YYYY-MM-DD / YYYY-MM-DD" | null
totals: { total_ventas: decimal, numero_transacciones: int } | null
extraction_status: "success" | "fallback_required"  → documents.ocr_status
errors: string[]
```

### ContextTag
```
clima: "lluvia" | "calor" | "frio" | null
equipo: "falla_maquina" | "mantenimiento" | null
evento: "festivo" | "obra_vial" | "promocion" | null
personal: "falta_staff" | "capacitacion" | null
otros: string | null
```

### MetricStatus
```
metric_name: string
status: "dormant" | "active"
missing_fields: string[]
```

### CalcResult
```
metric_name: string
value: decimal
unit: "%" | "MXN" | "unidades"
delta: decimal | null
period_ref: string
```

### AuditInsight (extiende AgentResult)
```
module, raw_result, copilot_phrase, archetype  // base
alert_level: "info" | "warning" | "critical"
recommended_action: string | null
context_weight: "reducido" | "normal" | "amplificado"
```

### AgentResult (base)
```
module: string
raw_result: string
copilot_phrase: string
archetype: "Operative Genius" | "Product Purist" | "Growth Hacker"
```

## Índices relevantes

| Índice                              | Tipo  | Tabla           | Para qué |
|-------------------------------------|-------|-----------------|----------|
| `idx_transactions_metadata`         | GIN   | transactions    | Búsquedas por campos dinámicos |
| `idx_documents_extracted`           | GIN   | documents       | Búsquedas en extracted_data |
| `idx_transactions_business_date`    | BTREE | transactions    | Consultas por negocio + fecha |
| `idx_documents_ocr_status`          | BTREE | documents       | Filtrar por estado OCR |
| `idx_daily_context_business_date`   | BTREE | daily_context   | Contexto por negocio + fecha |
| `idx_metric_status_lookup`          | BTREE | metric_status   | Estado de métricas por día |
| `idx_recipes_business`              | BTREE | recipes         | Recetas por negocio |
