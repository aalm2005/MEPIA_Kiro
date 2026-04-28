# N10 — Context Builder (Constructor de Contexto Determinista)

**Capa:** Layer 3 — primer paso | **Anterior:** N06 Orquestador ADK | **Siguiente:** N11 Consultor Especialista
**Archivo de implementación:** `agents/context_builder.py`
**Tecnología:** Python puro — sin LLM, 100% determinista
**Patrón:** Transformador de datos — recibe `ParallelGatherResult`, emite `Enriched_Audit_Payload`

---

## Responsabilidad

Actuar como el preparador de datos de Layer 3. No analiza, no interpreta, no genera texto.
Su único trabajo es consolidar y comprimir el contexto financiero, operativo y de identidad
en un payload estructurado listo para que N11 lo consuma sin overhead de tokens.

```
N06 ParallelGatherResult
        │
        ↓
N10 Context Builder (Python determinista)
  ├─ Extrae ForensicReport + N09 result de ParallelGatherResult
  ├─ Ejecuta SQL Rollups según temporalidad
  ├─ Consulta MemoryService (brand_identity + historial)
  └─ Emite Enriched_Audit_Payload
        │
        ↓
N11 Consultor Especialista (LLM)
```

---

## Input

```python
class ContextBuilderInput(BaseModel):
    parallel_gather_result: ParallelGatherResult  # output completo de N06
    temporalidad: Literal["short", "medium", "long"]  # propagado desde OrchestratorRunPayload
```

### Extracción desde `ParallelGatherResult`

```python
# Datos base de Layer 1 (via sequential_context)
forensic_report  = parallel_gather_result.sequential_context.forensic_report
audit_insights   = parallel_gather_result.sequential_context.insights
calc_results     = parallel_gather_result.sequential_context.calc_results
context_tags     = parallel_gather_result.sequential_context.context_tags
archetype        = parallel_gather_result.archetype
business_id      = parallel_gather_result.business_id
date             = parallel_gather_result.date

# Resultado de N09 (único nodo activo en V1)
n09_result = next(
    (r for r in parallel_gather_result.node_results
     if r.node_id == "N09" and r.status == "success"),
    None
)

# N07 y N08 en V1: status="error", error_detail="not_implemented_v1"
# N10 los ignora silenciosamente — no genera warning por este código específico
```

---

## Mecánica Principal — Time-Series Rollups (SQL Dinámico)

La granularidad de las consultas SQL depende del parámetro `temporalidad`.

### Modos de agrupación

| `temporalidad` | Rango | Granularidad SQL | Casos de uso |
|----------------|-------|-----------------|--------------|
| `"short"` | 1–30 días | `GROUP BY dia` (o por hora si disponible) | Eficiencia de barra, horarios pico, varianza diaria |
| `"medium"` | 3–6 meses | `GROUP BY semana` | Tendencias, retención, ingeniería de menú, estacionalidad |
| `"long"` | 1 año | `GROUP BY mes` | Resúmenes CapEx, servicios estructurales, ciclo anual |

### Consultas por modo

**`short` — detalle diario:**
```sql
SELECT
    transaction_date AS periodo,
    SUM(amount) FILTER (WHERE type = 'ingreso') AS ingresos,
    SUM(amount) FILTER (WHERE type = 'egreso' AND expense_behavior = 'VARIABLE') AS gastos_variable,
    SUM(amount) FILTER (WHERE type = 'egreso' AND expense_behavior = 'FIXED') AS gastos_fijos,
    COUNT(*) AS num_transacciones
FROM transactions
WHERE business_id = :business_id
  AND transaction_date BETWEEN :date_start AND :date
  AND needs_human_review = false
GROUP BY transaction_date
ORDER BY transaction_date DESC
```

**`medium` — tendencia semanal:**
```sql
SELECT
    DATE_TRUNC('week', transaction_date) AS periodo,
    SUM(amount) FILTER (WHERE type = 'ingreso') AS ingresos,
    SUM(amount) FILTER (WHERE type = 'egreso') AS egresos,
    AVG(amount) FILTER (WHERE type = 'ingreso') AS ingreso_promedio_semanal
FROM transactions
WHERE business_id = :business_id
  AND transaction_date BETWEEN :date_start AND :date
  AND needs_human_review = false
GROUP BY DATE_TRUNC('week', transaction_date)
ORDER BY periodo DESC
```

**`long` — resumen mensual:**
```sql
SELECT
    DATE_TRUNC('month', transaction_date) AS periodo,
    SUM(amount) FILTER (WHERE type = 'egreso' AND expense_behavior = 'CAPEX') AS capex_mes,
    SUM(amount) FILTER (WHERE type = 'ingreso') AS ingresos_mes,
    SUM(amount) FILTER (WHERE type = 'egreso') AS egresos_mes
FROM transactions
WHERE business_id = :business_id
  AND transaction_date BETWEEN :date_start AND :date
  AND needs_human_review = false
GROUP BY DATE_TRUNC('month', transaction_date)
ORDER BY periodo DESC
```

### Cálculo de `date_start` por `temporalidad`

```python
date_start = {
    "short":  date - timedelta(days=30),
    "medium": date - timedelta(days=180),
    "long":   date - timedelta(days=365),
}[temporalidad]
```

---

## Inyección de Identidad de Marca (MemoryService)

N10 consulta `MemoryService.get_context()` con dos queries distintas:

```python
# 1. Identidad de marca (fija, independiente del arquetipo)
brand_context = await memory_service.get_context(
    query="brand_identity lente CEO hospitalidad invisible espacio seguro",
    business_id=business_id,
    limit=3
)

# 2. Historial de auditorías recientes (contextual)
historical_context = await memory_service.get_context(
    query=f"auditoria financiera {archetype} anomalias gastos",
    business_id=business_id,
    limit=5
)
```

### Identidad de marca en `mepia_memory`

El "Lente del CEO" se inserta en `mepia_memory` durante el onboarding como un `MemoryChunk` especial:

```python
MemoryChunk(
    business_id=business_id,
    source_audit_run_id=None,   # null — no proviene de una auditoría
    node_origin="onboarding",   # valor especial para identidad de marca
    date=opening_date,
    content="""
        Identidad de marca: hospitalidad invisible.
        Principios: humildad, espacio seguro, experiencia sin fricción.
        PROHIBIDO en recomendaciones: tácticas de fidelización ostentosas,
        mecánicas estilo casino, marketing agresivo o pretencioso.
        El análisis debe priorizar la experiencia del cliente sobre métricas de conversión.
    """,
    archetype=archetype,
    quality_approved=True
)
```

> En V1, este chunk puede insertarse manualmente en `mepia_memory` durante el setup del negocio.
> En versiones posteriores, el onboarding lo generará automáticamente.

La identidad de marca es **fija e independiente del arquetipo** — se aplica a todos los análisis
sin importar si el dueño es `Operative Genius`, `Product Purist` o `Growth Hacker`.

---

## Output — `Enriched_Audit_Payload`

```python
class TimeSeriesRollup(BaseModel):
    temporalidad: Literal["short", "medium", "long"]
    date_start: date
    date_end: date
    granularidad: Literal["dia", "semana", "mes"]
    periodos: list[dict]   # filas del resultado SQL — estructura varía por granularidad


class ParallelNodeSummary(BaseModel):
    n09_available: bool
    n09_result: Optional[FinancialAuditResult]   # None si N09 falló
    n07_status: Literal["not_implemented_v1", "success", "error"]
    n08_status: Literal["not_implemented_v1", "success", "error"]
    all_warnings: list[str]   # warnings agregados de nodos disponibles


class BrandIdentityBlock(BaseModel):
    retrieved: bool          # false si mepia_memory no tiene chunk de onboarding
    content: str             # texto del Lente del CEO — vacío si retrieved=false
    fallback_used: bool      # true si se usó identidad genérica por ausencia de chunk


class Enriched_Audit_Payload(BaseModel):
    # Trazabilidad
    layer2_run_id: UUID
    sequential_run_id: UUID
    business_id: UUID
    date: date
    archetype: Literal["Operative Genius", "Product Purist", "Growth Hacker"]
    temporalidad: Literal["short", "medium", "long"]

    # Diagnóstico base (S4 via N06)
    forensic_report: ForensicReport

    # Insights CEO (N05 via N06)
    audit_insights: list[AuditInsightItem]

    # Rollups temporales (SQL dinámico)
    time_series: TimeSeriesRollup

    # Estado de nodos paralelos
    parallel_summary: ParallelNodeSummary

    # Identidad de marca (MemoryService)
    brand_identity: BrandIdentityBlock

    # Historial RAG
    historical_context: str   # string consolidado de MemoryService para N11

    # Metadata de construcción
    built_at: datetime
    build_duration_ms: int
```

---

## Contratos que requieren actualización

Este nodo introduce `temporalidad` como campo nuevo. Los siguientes contratos deben actualizarse:

| Contrato | Archivo | Cambio |
|----------|---------|--------|
| `OrchestratorRunPayload` | `n05_ceo_orchestrator.md` | Agregar `temporalidad: Literal["short","medium","long"] = "short"` |
| `Layer2RunPayload` | `n06_orchestrator_adk.md` | Agregar `temporalidad: Literal["short","medium","long"]` |
| `ParallelGatherResult` | `n06_orchestrator_adk.md` + `_glossary.md` | Agregar `temporalidad: Literal["short","medium","long"]` |

---

## Acceptance Criteria

- WHEN `temporalidad == "short"` → SQL usa `GROUP BY transaction_date`, rango 30 días
- WHEN `temporalidad == "medium"` → SQL usa `GROUP BY DATE_TRUNC('week', ...)`, rango 180 días
- WHEN `temporalidad == "long"` → SQL usa `GROUP BY DATE_TRUNC('month', ...)`, rango 365 días
- WHEN N07/N08 tienen `error_detail: "not_implemented_v1"` → ignorados silenciosamente, sin warning
- WHEN N09 tiene `status: "success"` → `parallel_summary.n09_available: true`, datos incluidos
- WHEN N09 tiene `status: "error"` o `"timeout"` → `parallel_summary.n09_available: false`, `n09_result: null`
- WHEN `mepia_memory` tiene chunk `node_origin: "onboarding"` → `brand_identity.retrieved: true`
- WHEN no hay chunk de onboarding → `brand_identity.fallback_used: true`, contenido genérico
- WHEN `needs_human_review = true` en transacciones → excluidas del rollup SQL
- WHEN N10 completa → `Enriched_Audit_Payload` entregado a N11, nunca `ParallelGatherResult` crudo

---

## Edge Cases

- `temporalidad` no enviado → default `"short"`, no error
- N09 timeout → `n09_available: false`, N11 recibe advertencia en `all_warnings`
- `mepia_memory` vacío (negocio nuevo) → `brand_identity.fallback_used: true`, análisis continúa
- Sin transacciones en el rango → `time_series.periodos: []`, N11 recibe contexto vacío con nota
- `MemoryService` no disponible → `historical_context: ""`, `brand_identity.retrieved: false`, continúa

---

## Correctness Properties (PBT)

| ID | Propiedad |
|----|-----------|
| P1 | `temporalidad == "short"` → `time_series.granularidad == "dia"` siempre |
| P2 | `temporalidad == "medium"` → `time_series.granularidad == "semana"` siempre |
| P3 | `temporalidad == "long"` → `time_series.granularidad == "mes"` siempre |
| P4 | N07/N08 con `error_detail: "not_implemented_v1"` → `all_warnings` no incluye mención de ellos |
| P5 | `Enriched_Audit_Payload.forensic_report` == `ParallelGatherResult.sequential_context.forensic_report` |
| P6 | `brand_identity.retrieved: true` → `brand_identity.fallback_used: false` siempre |
| P7 | `build_duration_ms` siempre > 0 y presente en el output |
| P8 | Transacciones con `needs_human_review = true` nunca aparecen en `time_series.periodos` |

---

## Archivos relacionados de este nodo
- `n06_orchestrator_adk.md` — `ParallelGatherResult` (input)
- `n05_ceo_orchestrator.md` — `OrchestratorRunPayload` (origen de `temporalidad`)
- `n11_consultor.md` — consumidor del `Enriched_Audit_Payload`
- `mem_memory_layer.md` — `MemoryService.get_context()` + chunk `node_origin: "onboarding"`
- `_glossary.md` — contratos `Enriched_Audit_Payload`, `TimeSeriesRollup`, `BrandIdentityBlock`
