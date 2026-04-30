# Diseño Frontend — MEPIA Dashboard & Upload

**Fase:** Diseño (Fase 2) | **Tipo:** Feature — Frontend UI
**Stack:** Next.js App Router · TypeScript · Tailwind CSS · Supabase · FastAPI

## Visión

Interfaz de auditoría financiera forense para restaurantes. Estética minimalista-brutalista:
herramienta de alta precisión, sin ruido visual. La jerarquía prioriza anomalías y márgenes
críticos sobre cualquier otro elemento.

## Rutas cubiertas

| Ruta | Componente raíz | Propósito |
|------|-----------------|-----------|
| `/app/upload` | `UploadPage` | Ingesta de documentos (POS + facturas) + selector de arquetipo |
| `/app/dashboard` | `DashboardPage` | Presentación del análisis forense + Layer 2 si escaló |
| `/app/onboarding` | `OnboardingPage` | Configuración inicial del negocio (prerequisito de Layer 3) |

**V1 — Auth:** Sin pantalla de login. El sistema arranca con un `business_id` hardcodeado en `.env.local`. La autenticación real se implementa en V2.

## Artefactos de diseño

Este documento es el índice. El detalle está distribuido en archivos hermanos:

| Archivo | Contenido |
|---------|-----------|
| `design_components.md` | Árbol de componentes React, props, contratos de UI |
| `design_system.md` | Design system: `tailwind.config.ts`, paleta, tipografía, tokens |
| `design_wireframes.md` | Wireframing lógico del dashboard, upload y onboarding |
| `design_flows.md` | Flujo de interacción completo: onboarding → ingesta → análisis → pantalla |

## Principios de diseño

1. **Datos forenses primero** — anomalías `critical` y `warning` resaltan sin acción del usuario
2. **Sin ruido** — cero decoración que no aporte información
3. **Brutalismo funcional** — bordes duros, tipografía monoespaciada para números, contraste máximo
4. **Arquetipo visible** — el badge de arquetipo CEO es parte del lenguaje visual, no un detalle

## Decisiones de arquitectura

- Server Components por defecto; solo formularios de upload y onboarding usan `"use client"`
- Dashboard consume `OrchestratorResult` vía polling o Supabase Realtime
- `AuditTable.tsx` soporta `AuditInsight[]` (N05) y `AgentResult[]` (paralelos)
- **V1 — Sin auth:** `NEXT_PUBLIC_BUSINESS_ID` en `.env.local` se inyecta en todas las llamadas a la API

## Contratos de UI relevantes

- `AuditInsight` — generado por N05, renderizado en `AuditTable`
- `ForensicReport.risk_level` — determina el banner de alerta global
- `OrchestratorResult.pipeline_status` — controla el estado de carga
- `OrchestratorResult.escalation` — activa `Layer2Banner` y nodo `[L2]`
- `POSIngestResult` / `FacturaIngestResult` — feedback post-upload
- `OnboardingStatusResponse.onboarding_complete` — controla `OnboardingGate`

Ver `_glossary.md` para los contratos completos.

## Archivos relacionados de este nodo

- `design_components.md` — cargar para implementar componentes React
- `design_system.md` — cargar para configurar Tailwind y tokens visuales
- `design_wireframes.md` — cargar para entender el layout antes de implementar
- `design_flows.md` — cargar para implementar la lógica de interacción y estados

## Gaps cubiertos (v1.1)

| Gap | Solución |
|-----|----------|
| `/app/onboarding` inexistente | Ruta, componentes, wireframe y flujo agregados |
| Selector de arquetipo CEO | `ArchetypeSelector` en `/app/upload` antes del CTA |
| Layer 2 sin representación | `Layer2Banner` + nodo `[L2]` en `PipelineStatusBar` |
| Auth V1 | Sin login — `NEXT_PUBLIC_BUSINESS_ID` en `.env.local` |
