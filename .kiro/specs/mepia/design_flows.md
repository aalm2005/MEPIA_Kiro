# Diseño Frontend — Flujo de Interacción

**Referenciado desde:** `design.md`

## Flujo completo: ingesta → análisis → pantalla

```mermaid
sequenceDiagram
    participant U as Usuario
    participant UP as /upload
    participant API as Next.js API Route
    participant FA as FastAPI
    participant DB as Supabase

    U->>UP: Selecciona PDF de POS
    U->>UP: Selecciona PDF/XML de factura
    U->>UP: Click "Analizar con Agentes IA"

    UP->>API: POST /api/upload (multipart: pos_file)
    API->>FA: POST /ingest/pos
    FA-->>DB: Persiste en documents + pos_inputs
    FA-->>API: POSIngestResult[]
    API-->>UP: { status, needs_human_review }

    alt needs_human_review: true
        UP->>U: ReviewAlert — campos faltantes
        U->>UP: Corrige campos manualmente
        UP->>API: PATCH /api/upload/review
        API->>FA: PATCH /ingest/pos/{file_id}/review
    end

    UP->>API: POST /api/audit (trigger pipeline)
    API->>FA: POST /orchestrator/run
    FA-->>API: { run_id, pipeline_status: "running" }
    API-->>UP: { run_id }
    UP->>U: Redirige a /dashboard?run_id=...

    loop Polling cada 2s
        UP->>API: GET /api/audit/status/{run_id}
        API->>FA: GET /orchestrator/status/{run_id}
        FA-->>API: { pipeline_status, current_node }
        API-->>UP: { status, currentNode }
        UP->>U: PipelineStatusBar actualiza nodo activo
    end

    FA-->>DB: Persiste OrchestratorResult
    UP->>API: GET /api/audit/result/{run_id}
    API->>FA: GET /orchestrator/result/{run_id}
    FA-->>API: OrchestratorResult
    API-->>UP: { auditInsights, forensicReport, dormantMetrics }
    UP->>U: Renderiza AuditTable + ForensicSummary
```

## Estados de la UI por `pipeline_status`

| `pipeline_status` | PipelineStatusBar | AuditTable | Banner |
|-------------------|-------------------|------------|--------|
| `running` | Animación en nodo activo | Skeleton loader | — |
| `completed` | Todos verdes | Datos reales | Según `risk_level` |
| `partial` | Verdes + grises (dormant) | Datos parciales | Info: métricas faltantes |
| `escalated` | Verdes + indicador Layer 2 | Datos + nota escalación | Warning |
| `failed` | Rojo en nodo fallido | Error state | Error crítico |

## Flujo de `risk_level` → UI

```
ForensicReport.risk_level
  │
  ├── "high"   → Banner rojo fijo en top del dashboard
  │              Filas critical con borde rojo
  │              AnomalyCards en panel lateral
  │
  ├── "medium" → Banner ámbar colapsable
  │              Filas warning con borde ámbar
  │
  └── "low"    → Sin banner
                 Solo métricas dormant en panel lateral
```

## Flujo de `needs_human_review`

```
POST /ingest/pos → POSIngestResult
  │
  ├── needs_human_review: false → continuar al trigger del pipeline
  │
  └── needs_human_review: true
        → ReviewAlert muestra missing_fields
        → Usuario completa campos
        → PATCH /ingest/pos/{file_id}/review
        → Si 200 → continuar al trigger del pipeline
        → Si error → mostrar mensaje específico
```

## Manejo de errores de API

| HTTP | Mensaje en UI | Componente |
|------|---------------|------------|
| 409 | "Faltan datos para iniciar el análisis. Revisa las métricas dormant." | Banner warning |
| 412 | "Completa el onboarding del negocio antes de auditar." | Banner con link |
| 503 | "El servicio de análisis no está disponible." | Banner error |
| 422 | Mensaje específico del campo inválido | Inline en formulario |

## Archivos relacionados de este nodo

- `design_components.md` — componentes que implementan cada estado del flujo
- `design_wireframes.md` — layouts donde ocurren las transiciones
