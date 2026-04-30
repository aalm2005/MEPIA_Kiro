# Diseño Frontend — Flujos de Interacción

**Referenciado desde:** `design.md`

## Índice de flujos

| Archivo | Flujo |
|---------|-------|
| `design_flows_main.md` | Diagrama de secuencia completo: onboarding → ingesta → análisis → pantalla |
| Este archivo | Estados de UI, flujos de control, errores, V1 auth |

## Estados de la UI por `pipeline_status`

| `pipeline_status` | PipelineStatusBar | AuditTable | Banner |
|-------------------|-------------------|------------|--------|
| `running` | Animación en nodo activo | Skeleton loader | — |
| `completed` | Todos verdes | Datos reales | Según `risk_level` |
| `partial` | Verdes + grises (dormant) | Datos parciales | Info: métricas faltantes |
| `escalated` | Verdes + nodo `[L2]` activo | Datos reales + nota escalación | `Layer2Banner` ámbar |
| `failed` | Rojo en nodo fallido | Error state | Error crítico |

## Flujo de onboarding

```
App arranca → /upload carga
  │
  └─ OnboardingGate: GET /business/{id}/onboarding/status
        ├── onboarding_complete: true → UploadForm visible
        └── onboarding_complete: false
              → OnboardingRequiredBanner → CTA "Configurar negocio →"
              → /onboarding → 4 pasos → POST /business/{id}/onboarding
              → HTTP 201 → redirige a /upload → UploadForm visible
```

## Flujo de Layer 2 (escalation)

```
OrchestratorResult.escalation.triggered: true
  ├── Layer2Banner aparece (ámbar, colapsable)
  ├── PipelineStatusBar agrega nodo [L2] con spinner
  └── Polling sobre layer2_run_id
        ├── "running"   → spinner en [L2]
        ├── "completed" → checkmark verde + "Ver análisis profundo →"
        └── "failed"    → rojo en [L2] + mensaje de error
```

## Flujo de `risk_level` → UI

```
ForensicReport.risk_level
  ├── "high"   → Banner rojo fijo + filas critical + AnomalyCards
  ├── "medium" → Banner ámbar colapsable + filas warning
  └── "low"    → Sin banner, solo métricas dormant
```

## Flujo de `needs_human_review`

```
POST /ingest/pos → POSIngestResult
  ├── false → continuar al trigger del pipeline
  └── true  → ReviewAlert con missing_fields
               → PATCH /ingest/pos/{file_id}/review
               → 200 → continuar | error → mensaje específico
```

## Manejo de errores de API

| HTTP | Mensaje en UI | Componente |
|------|---------------|------------|
| 409 | "Faltan datos para iniciar el análisis." | Banner warning |
| 412 | "Completa el onboarding antes de auditar." | `OnboardingRequiredBanner` |
| 503 | "El servicio no está disponible." | Banner error |
| 422 | Mensaje del campo inválido | Inline en formulario |

## V1 — Sin autenticación

`NEXT_PUBLIC_BUSINESS_ID` en `.env.local` se inyecta como constante en todas las
llamadas a la API. El backend en `ENVIRONMENT=dev` acepta requests sin JWT.

## Archivos relacionados de este nodo

- `design_flows_main.md` — diagrama de secuencia completo
- `design_components.md` — componentes que implementan cada estado
- `design_wireframes.md` — layouts donde ocurren las transiciones
