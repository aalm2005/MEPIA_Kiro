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
  │ S4: NODO DE AUDITORÍA (IA)                              │
  │   Input: resultados Python + tags de contexto           │
  │   Pondera alertas según contexto                        │
  │   Output: insight CEO-framed con acción recomendada     │
  └─────────────────────────────────────────────────────────┘
        ↓
[Layer 2: Parallel]   Orquestador → Conciliación | PLD | Gastos | Auditor Agent
        ↓
[Layer 3: Loop/Critic] Consultor → Auditor Agent → Phrase Expander → Revisor → Informe Final
```

## Nodos y archivos de spec

| ID   | Nodo                    | Capa       | Archivo                    | Estado      |
|------|-------------------------|------------|----------------------------|-------------|
| S1   | Ingesta (5 inputs)      | Sequential | `s1_ingesta.md`            | ✅ req done  |
| N02  | Facturas Proveedor Input| Sequential | `n02_facturas_input.md`    | ✅ req done  |
| N03  | Human Input Endpoints   | Sequential | `n03_human_input_endpoints.md` | ✅ req done |
| S2   | Stand-by / Gatekeeper   | Sequential | `s2_gatekeeper.md`         | ✅ req done  |
| S3   | Motor de Cálculo        | Sequential | `s3_motor_calculo.md`      | ✅ req done  |
| S4   | Nodo de Auditoría IA    | Sequential | `s4_auditoria_ia.md`       | ✅ req done  |
| N05  | CEO Orchestrator        | CEO Layer  | `n05_ceo_orchestrator.md`  | ✅ req done |
| N06  | Orquestador ADK         | Parallel   | `n06_orchestrator_adk.md`  | ✅ req done |
| N07  | Conciliación Efectivo   | Parallel   | `n07_conciliacion.md`      | pendiente   |
| N08  | Cumplimiento PLD        | Parallel   | `n08_pld.md`               | pendiente   |
| N09  | Auditoría Gastos        | Parallel   | `n09_gastos.md`            | ✅ req done |
| N10  | Auditor Agent           | Parallel   | `n10_auditor_agent.md`     | pendiente   |
| N11  | Consultor Especialista  | Loop       | `n11_consultor.md`         | pendiente   |
| N12  | Phrase Expander         | Loop       | `n12_phrase_expander.md`   | pendiente   |
| N13  | Revisor de Calidad      | Loop       | `n13_revisor.md`           | pendiente   |
| N14  | Informe Final           | Loop       | `n14_informe_final.md`     | pendiente   |
| MEM  | Memory Layer            | Transversal| `mem_memory_layer.md`      | pendiente   |

## Contratos de datos clave

- **POSIngestResult** → `n01_pos_pdf_input.md`
- **FacturaIngestResult** → `n02_facturas_input.md`
- **ContextTag** → `s1_ingesta.md`
- **MetricStatus** (dormant/active) → `s2_gatekeeper.md`
- **CalcResult** → `s3_motor_calculo.md`
- **AuditInsight** → `s4_auditoria_ia.md`
- **OrchestratorResult** → `n05_ceo_orchestrator.md`
- **AgentResult** → `agents/base_agent.py`

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
| S4 auditoría  | `agents/audit_node.py`                   |

## Schema de base de datos

- **Arquitectura híbrida** → `db_schema.md`
- Tablas: `businesses`, `business_fixed_costs`, `documents`, `transactions`, `pos_inputs`, `cash_counts`, `recipes`, `daily_context`, `metric_status`, `unit_conversions`, `audit_results`
- JSONB: `extracted_data`, `metadata`, `raw_metadata`, `tags`, `ingredients`, `missing_fields`
- Campos clave nuevos: `expense_behavior` (FIXED/VARIABLE/CAPEX), `needs_human_review`, `ocr_confidence`, `raw_metadata`

## Reglas de carga de contexto

Al implementar un nodo, cargar SOLO:
1. `_index.md` + `_glossary.md`
2. El archivo del nodo específico
3. Los archivos de código directamente relacionados
