# MEPIA — Glosario Compartido

## Términos del dominio

| Término              | Definición |
|----------------------|------------|
| POS_PDF              | Reporte diario de ventas del sistema de punto de venta |
| Ticket diario        | Sinónimo de POS_PDF |
| Metadata             | `business_name`, `period`, `totals` extraídos del POS_PDF |
| SharedHeader         | Subconjunto de Metadata para agentes paralelos: `business_name`, `period`, `totals` |
| CEO Archetype        | Perfil del dueño: `Operative Genius` \| `Product Purist` \| `Growth Hacker` |
| CEO Cognitive Frame  | Lente + blind spots + question set inyectado en system prompt de cada agente |
| Q-Framework          | 5 preguntas del Auditor Agent: constraint, margin leak, ignored data, 3x scale, bottleneck |
| AgentResult          | Output estándar de todo agente: `module`, `raw_result`, `copilot_phrase`, `archetype` |
| Warning              | Señal de anomalía generada por agente paralelo, recolectada para Loop/Critic |
| Informe Final        | Output terminal: expandido, validado, CEO-framed |
| BOM                  | Bill of Materials — Receta técnica de un producto con ingredientes y cantidades |
| expense_behavior     | Clasificación de gasto: `FIXED` \| `VARIABLE` \| `CAPEX` — confirmada vía `PATCH /transactions/{id}/expense-behavior` |
| needs_human_review   | Flag en `documents`: true si OCR < 85% de confianza o campo obligatorio ausente |
| initial_float        | Fondo inicial del cajón al abrir el día |
| raw_metadata         | JSONB en `transactions` con campos extraídos fuera del mapeo obligatorio (future-proofing) |

## Componentes de infraestructura

| Componente           | Tecnología        | Responsabilidad |
|----------------------|-------------------|-----------------|
| Ingest_Service       | FastAPI           | Valida, persiste, parsea documentos — endpoints en `n01`, `n02`, `n03` |
| Ingesta Worker       | Python + Pydantic | Extrae, valida esquema, infiere category, evalúa confianza OCR |
| Storage              | Supabase Storage  | Persiste PDFs/XML en `pos-tickets/` y `facturas/` |
| mepia.db             | SQLite            | Memoria estructurada: audit_runs, daily_metrics, ceo_insights, warnings_log |
| Memory_Writer        | Python module     | Escribe JSON en mepia.db tras Sequential pipeline |
| Memory_Reader        | Python module     | Lee últimos N días + deltas para Auditor Agent |
| RAG_KB               | Vector store      | Entrevistas de auditores + NIIF |
| Prompt Dictionary    | Python dict/YAML  | Templates de arquetipo para S4 — prohíbe frases genéricas |
| Engram               | Binario Go (local)| Memoria de largo plazo (CAS). Requiere compilar el repo Engram y tener el binario en PATH. Configurado como servidor MCP en `.kiro/settings/mcp.json` con `{"command": "engram", "args": ["mcp"]}`. Expone herramientas `search` (read) y `store` (write). |
| MemoryService        | Python (`utils/memory_service.py`) | Wrapper que abstrae pgvector + Engram. Expone `get_context()` (read, todos los agentes) y `store_memory()` (write, solo N12/N13). |
| mepia_vector_store   | Supabase pgvector | Tabla de embeddings semánticos ("Brain"). Solo para LangChain RAG. Embedding: `text-embedding-3-small` 1536 dims. NO es el Ledger del dashboard. |

## Base de datos — Tablas

| Tabla                  | Propósito |
|------------------------|-----------|
| `businesses`           | Entidad raíz con `operating_hours` |
| `business_fixed_costs` | Gastos fijos del onboarding con `expense_behavior` y `recurrence` |
| `documents`            | Archivos subidos con `ocr_confidence`, `needs_human_review`, `extracted_data` |
| `transactions`         | Datos financieros con `expense_behavior`, `raw_metadata`, `supplier_name`, `tax_amount` |
| `pos_inputs`           | Ventas diarias POS: `cash_sales`, `card_sales`, `refunds` |
| `cash_counts`          | Conteo físico del cajón: `initial_float`, `actual_counted`, `cash_payouts` |
| `recipes`              | BOM por producto con `sale_price` e `ingredients` (JSONB) |
| `daily_context`        | Tags de contexto del día (JSONB) |
| `metric_status`        | Estado `dormant`/`active`/`blocked` por métrica, negocio y fecha |
| `unit_conversions`     | Catálogo de conversiones de unidades para el Motor de Cálculo |
| `audit_results`        | Outputs de todos los nodos del pipeline con `pipeline_layer`, `node_id`, `node_status` |
| `mepia_vector_store`   | Embeddings semánticos para LangChain RAG ("Brain"). Escritura solo desde N12/N13. |

## Campos JSONB clave

| Campo            | Tabla           | Contenido |
|------------------|-----------------|-----------|
| `extracted_data` | `documents`     | Respuesta cruda del agente IA |
| `metadata`       | `transactions`  | Datos extra por tipo de documento |
| `raw_metadata`   | `transactions`  | Todo campo extraído fuera del mapeo obligatorio |
| `tags`           | `daily_context` | `{ clima, equipo, evento, personal, otros }` |
| `ingredients`    | `recipes`       | `{ cafe_g: 18, leche_ml: 250 }` |
| `missing_fields` | `metric_status` | Lista de datos faltantes para activar la métrica |
| `operating_hours`| `businesses`    | `{ open: "08:00", close: "22:00" }` |

## Estados de métricas (Gatekeeper S2)

| Estado    | Significado                                                  |
|-----------|--------------------------------------------------------------|
| `dormant` | Faltan datos. No se calcula en S3.                           |
| `active`  | Set completo. Pasa al Motor de Cálculo.                      |
| `blocked` | Documento pendiente de revisión humana (`needs_human_review`)|

## Status de CalcResult (Motor S3)

| Status            | Significado                                              |
|-------------------|----------------------------------------------------------|
| `ok`              | Dentro de umbrales normales                              |
| `warning`         | En zona de atención                                      |
| `critical`        | Fuera de umbral crítico                                  |
| `incomplete_data` | Faltan datos o división por cero                         |
| `unit_mismatch`   | Unidades incompatibles entre receta y factura            |

## Normalización de unidades

| Unidad origen | Unidad base | Factor |
|---------------|-------------|--------|
| kg            | g           | × 1000 |
| L             | ml          | × 1000 |
| unidad        | unidad      | × 1    |

## Contratos de datos

### DailyContextPayload
```
business_id: UUID
date: YYYY-MM-DD
tags: {
  clima: "lluvia" | "calor" | "frio" | null
  equipo: "falla_maquina" | "mantenimiento" | null
  evento: "festivo" | "obra_vial" | "promocion" | null
  personal: "falta_staff" | "capacitacion" | null
  otros: string | null (max 500 chars)
}
```

### FacturaIngestResult
```
file_id: UUID
storage_path: string
extraction_status: "success" | "needs_human_review"
needs_human_review: bool
ocr_confidence: float | null       # null para XML
transaction_id: UUID | null        # null si needs_human_review
extracted_fields: ExtractedFacturaFields | null
missing_fields: string[] | null
```

### ExpenseBehaviorPayload
```
expense_behavior: "FIXED" | "VARIABLE" | "CAPEX"
confirmed_by: UUID
force: bool (opcional, default false)
```

### CashCountPayload
```
business_id: UUID
date: YYYY-MM-DD
initial_float: Decimal (≥ 0)
actual_counted: Decimal (≥ 0)
cash_payouts: Decimal (≥ 0, default 0)
recorded_by: UUID
```

### OnboardingPayload
```
business_name: string
industry_sector: string
currency: string (ISO 4217, default "MXN")
operating_hours: { open: "HH:MM", close: "HH:MM" }
fixed_costs: FixedCostItem[] (mínimo 1)
```

### ParallelGatherResult
```
layer2_run_id: UUID
sequential_run_id: UUID
business_id: UUID
date: YYYY-MM-DD
archetype: "Operative Genius" | "Product Purist" | "Growth Hacker"
node_results: NodeResult[3]     # siempre 3 elementos
summary: {
  total_nodes: 3
  succeeded: int
  timed_out: int
  failed: int
  all_warnings: string[]
}
gather_status: "complete" | "partial" | "failed"
completed_at: datetime
```

### NodeResult
```
node_id: "N07" | "N08" | "N09"
node_name: "conciliacion" | "pld" | "gastos"
status: "success" | "timeout" | "error"
result: AgentResult | null
warnings: string[]
error_detail: string | null     # "circuit_open" si nodo degradado
duration_ms: int
```

### Layer2RunPayload
```
layer2_run_id: UUID
sequential_run_id: UUID
business_id: UUID
date: YYYY-MM-DD
archetype: "Operative Genius" | "Product Purist" | "Growth Hacker"
sequential_context: SequentialContext
node_timeouts: {
  n07_conciliacion: int (default 15s)
  n08_pld:          int (default 60s)
  n09_gastos:       int (default 20s)
}
```

### OrchestratorResult
```
run_id: UUID
business_id: UUID
date: YYYY-MM-DD
archetype: "Operative Genius" | "Product Purist" | "Growth Hacker"
pipeline_status: "completed" | "partial" | "escalated" | "failed"
sequential_results: { active_metrics, calc_results, audit_insights }
escalation: { triggered: bool, reason: str | null, layer2_run_id: UUID | null }
dormant_metrics: [{ metric, missing: string[] }]
completed_at: datetime
```

### AuditRunPayload
```
business_id: UUID
date: YYYY-MM-DD
archetype: "Operative Genius" | "Product Purist" | "Growth Hacker"  # default: Operative Genius
```

### POSIngestResult
```
file_id: UUID                    → documents.id
storage_path: string             → documents.storage_path
extraction_status: "success" | "fallback_required" | "needs_human_review"
extracted_data: JSONB | null     → documents.extracted_data
uploaded_at: datetime (UTC ISO-8601)
needs_human_review: bool
```

### GatekeeperResult
```
business_id: UUID
date: YYYY-MM-DD
active_metrics: string[]
dormant_metrics: [{ metric, missing: string[] }]
blocked_metrics: [{ metric, reason: "needs_human_review" }]
```

### CalcResult
```
metric: string
value: decimal | null
unit: string
status: "ok"|"warning"|"critical"|"incomplete_data"|"unit_mismatch"
context: string
```

### AuditInsight (extiende AgentResult)
```
module, raw_result, copilot_phrase, archetype   // base
alert_level: "info" | "warning" | "critical"
recommended_action: string
context_weight: "reducido" | "normal" | "amplificado"
```

### AgentResult (base)
```
module: string
raw_result: string
copilot_phrase: string
archetype: "Operative Genius" | "Product Purist" | "Growth Hacker"
```

### MemoryChunk
Payload que N12 o N13 envían a `MemoryService.store_memory()` al final de Layer 3.
```
business_id: UUID
node_origin: "N12" | "N13"
date: YYYY-MM-DD
content: string          # texto del reporte consolidado / insight final
archetype: "Operative Genius" | "Product Purist" | "Growth Hacker"
quality_approved: bool   # true si N13 validó el contenido
```
