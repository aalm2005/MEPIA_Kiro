# MEPIA — Índice del Sistema

## Pipeline redefinido (Sequential Layer)

```
[CEO Orchestrator Layer]
        ↓
[Layer 1: Sequential — 3 sub-nodos]

  ┌─────────────────────────────────────────────────────────┐
  │ S1: INGESTA (5 inputs)                                  │
  │   POS/PDF → OCR → documents + transactions              │
  │   Recipes (BOM) → tabla recipes                         │
  │   Contexto del día → tags + texto libre → metadata JSONB│
  └──────────────────┬──────────────────────────────────────┘
                     ↓
  ┌─────────────────────────────────────────────────────────┐
  │ S2: STAND-BY / GATEKEEPER                               │
  │   Valida integridad de datos por métrica                │
  │   Estado: dormant (faltan datos) → active (set completo)│
  └──────────────────┬──────────────────────────────────────┘
                     ↓
  ┌─────────────────────────────────────────────────────────┐
  │ S3: MOTOR DE CÁLCULO (Python puro)                      │
  │   Cálculos financieros sobre métricas active            │
  │   Output: números crudos sin interpretación             │
  └──────────────────┬──────────────────────────────────────┘
                     ↓
  ┌─────────────────────────────────────────────────────────┐
  │ S4: FORENSIC CFO (IA)                                   │
  │   Input: CalcResult[] + daily_context tags              │
  │   Diagnóstico forense: fugas, discrepancias, techos     │
  │   Output: ForensicReport — sin recomendaciones          │
  └─────────────────────────────────────────────────────────┘
        ↓
[CEO Orchestrator Layer — N05]
  Recibe ForensicReport + memoria RAG
  Aplica arquetipo CEO → genera AuditInsight[] con copilot_phrase
        ↓
[Layer 2: Parallel]   Orquestador → N09 Gastos (N07/N08 skipped_v1)
        ↓
[Layer 3: Loop/Critic] N10 Context Builder → N11 Consultor → N12 Phrase Expander → N13 Revisor → N14 Informe Final
```

## Nodos y archivos de spec

| ID   | Nodo                    | Capa       | Archivo                    | Estado      |
|------|-------------------------|------------|----------------------------|-------------|
| S1   | Ingesta (5 inputs)      | Sequential | `s1_ingesta.md`            | ✅ req done  |
| N02  | Facturas Proveedor Input| Sequential | `n02_facturas_input.md`    | ✅ req done  |
| N03  | Human Input Endpoints   | Sequential | `n03_human_input_endpoints.md` | ✅ req done |
| S2   | Stand-by / Gatekeeper   | Sequential | `s2_gatekeeper.md`         | ✅ req done  |
| S3   | Motor de Cálculo        | Sequential | `s3_motor_calculo.md`      | ✅ req done  |
| S4   | Forensic CFO (Auditoría IA) | Sequential | `s4_auditoria_ia.md`       | ✅ req done  |
| N05  | CEO Orchestrator (Síntesis Estratégica) | CEO Layer  | `n05_ceo_orchestrator.md`  | ✅ req done |
| N06  | Orquestador ADK         | Parallel   | `n06_orchestrator_adk.md`  | ✅ req done |
| N07  | Conciliación Efectivo   | Parallel   | `n07_conciliacion.md`      | skipped_v1  |
| N08  | Cumplimiento PLD        | Parallel   | `n08_pld.md`               | skipped_v1  |
| N09  | Auditoría Gastos        | Parallel   | `n09_gastos.md`            | ✅ req done |
| N10  | Context Builder (Layer 3)| Loop      | `n10_context_builder.md`   | ✅ req done |
| N11  | Consultor Especialista  | Loop       | `n11_consultor.md`         | pendiente   |
| N12  | Phrase Expander         | Loop       | `n12_phrase_expander.md`   | pendiente   |
| N13  | Revisor de Calidad      | Loop       | `n13_revisor.md`           | pendiente   |
| N14  | Informe Final           | Loop       | `n14_informe_final.md`     | pendiente   |
| MEM  | Memory Layer            | Transversal| `mem_memory_layer.md`      | ✅ req done |

## Contratos de datos clave

- **POSIngestResult** → `n01_pos_pdf_input.md`
- **FacturaIngestResult** → `n02_facturas_input.md`
- **ContextTag** → `s1_ingesta.md`
- **MetricStatus** (dormant/active) → `s2_gatekeeper.md`
- **CalcResult** → `s3_motor_calculo.md`
- **ForensicReport** → `s4_auditoria_ia.md`
- **AuditInsight** → `n05_ceo_orchestrator.md` (generado por N05, no por S4)
- **Enriched_Audit_Payload** → `n10_context_builder.md`
- **OrchestratorResult** → `n05_ceo_orchestrator.md`
- **AgentResult** → `agents/base_agent.py`
- **MemoryChunk** → `mem_memory_layer.md`

## Archivos de implementación (referencia)

| Spec          | Archivo de código                        |
|---------------|------------------------------------------|
| N01           | `api/main.py` + `app/api/upload/route.ts`|
| N02           | `api/main.py` → `POST /ingest/factura`   |
| N03           | `api/main.py` → `/transactions`, `/cash-counts`, `/onboarding` |
| N05           | `api/main.py` → `POST /orchestrator/run`, `GET /orchestrator/status/{run_id}` |
| N06           | `agents/parallel_orchestrator.py` → LangGraph StateGraph / LCEL RunnableParallel |
| N09           | `agents/business_health.py`                              |
| S2 gatekeeper | `agents/gatekeeper.py`                   |
| S3            | `agents/calc_engine.py`                  |
| S4 forensic CFO     | `agents/forensic_cfo.py`                 |
| N10 context builder | `agents/context_builder.py`              |

## Schema de base de datos

- **Arquitectura híbrida** → `db_schema.md`
- Tablas: `businesses`, `business_fixed_costs`, `documents`, `transactions`, `pos_inputs`, `cash_counts`, `recipes`, `daily_context`, `metric_status`, `unit_conversions`, `audit_results`, `circuit_breaker_state`, `mepia_memory`
- JSONB: `extracted_data`, `metadata`, `raw_metadata`, `tags`, `ingredients`, `missing_fields`
- Campos clave nuevos: `expense_behavior` (FIXED/VARIABLE/CAPEX), `needs_human_review`, `ocr_confidence`, `raw_metadata`

## Reglas de carga de contexto

Al implementar un nodo, cargar SOLO:
1. `_index.md` + `_glossary.md`
2. El archivo del nodo específico
3. Los archivos de código directamente relacionados
