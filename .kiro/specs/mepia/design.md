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
| `/app/upload` | `UploadPage` | Ingesta de documentos (POS + facturas) |
| `/app/dashboard` | `DashboardPage` | Presentación del análisis forense |

## Artefactos de diseño

Este documento es el índice. El detalle está distribuido en archivos hermanos:

| Archivo | Contenido |
|---------|-----------|
| `design_components.md` | Árbol de componentes React, props, contratos de UI |
| `design_system.md` | Design system: `tailwind.config.ts`, paleta, tipografía, tokens |
| `design_wireframes.md` | Wireframing lógico del dashboard y upload |
| `design_flows.md` | Flujo de interacción completo: ingesta → análisis → pantalla |

## Principios de diseño

1. **Datos forenses primero** — anomalías `critical` y `warning` resaltan sin acción del usuario
2. **Sin ruido** — cero decoración que no aporte información
3. **Brutalismo funcional** — bordes duros, tipografía monoespaciada para números, contraste máximo
4. **Arquetipo visible** — el badge de arquetipo CEO es parte del lenguaje visual, no un detalle

## Decisiones de arquitectura

- Todas las rutas son **Server Components** por defecto; solo los formularios de upload usan `"use client"`
- El dashboard consume `OrchestratorResult` vía `GET /orchestrator/status/{run_id}` o datos persistidos en Supabase
- `AuditTable.tsx` se extiende para soportar `AuditInsight[]` (N05) además de `AgentResult[]` (paralelos)
- El estado de carga del pipeline se refleja en tiempo real con polling o Supabase Realtime

## Contratos de UI relevantes

Los contratos de datos que la UI consume directamente:

- `AuditInsight` — generado por N05, renderizado en `AuditTable`
- `ForensicReport.risk_level` — determina el banner de alerta global del dashboard
- `OrchestratorResult.pipeline_status` — controla el estado de carga
- `POSIngestResult` / `FacturaIngestResult` — feedback post-upload en `/upload`

Ver `_glossary.md` para los contratos completos.

## Archivos relacionados de este nodo

- `design_components.md` — cargar para implementar componentes React
- `design_system.md` — cargar para configurar Tailwind y tokens visuales
- `design_wireframes.md` — cargar para entender el layout antes de implementar
- `design_flows.md` — cargar para implementar la lógica de interacción y estados
