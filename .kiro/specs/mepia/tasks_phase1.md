# Fase 1 — Design System + Componentes Base + Onboarding

## Tareas

- [x] 1. Actualizar `tailwind.config.ts` con design system brutalista
  - Reemplazar el contenido actual con la config de `design_system.md`
  - Agregar colores `canvas`, `surface`, `elevated`, `border`, `muted`
  - Agregar semáforo forense: `critical`, `warning`, `info`
  - Agregar colores de arquetipos: `archetype.operative/purist/hacker`
  - Agregar fuente `mono` (JetBrains Mono), escalas `forensic-xl/lg`, `label`
  - Agregar `spacing.panel/row`, `borderWidth.alert`, `boxShadow.panel/glow-critical`
  - _Requirements: design_system.md_

- [x] 2. Actualizar `app/globals.css` y `app/layout.tsx`
  - Cambiar `bg-zinc-900` por `bg-canvas` en `layout.tsx`
  - Importar `@fontsource/jetbrains-mono` o declarar `@font-face` en globals.css
  - Verificar que `font-sans` y `font-mono` resuelven correctamente
  - _Requirements: design_system.md_

- [x] 3. Crear `components/ui/ArchetypeBadge.tsx`
  - Props: `archetype: "Operative Genius" | "Product Purist" | "Growth Hacker"`
  - Aplicar tokens de `archetypeBadge` del design system
  - Reemplazar el mapa inline en `AuditTable.tsx` por este componente
  - _Requirements: design_components.md, design_system.md_

- [x] 4. Crear `components/ui/AlertLevelBadge.tsx`
  - Props: `level: "critical" | "warning" | "info"`
  - Aplicar tokens de `alertBadge` del design system
  - Exportar también el mapa `alertBadge` como constante reutilizable
  - _Requirements: design_system.md, design_components_tree.md_

- [x] 5. Crear `app/onboarding/page.tsx` y `components/onboarding/OnboardingForm.tsx`
  - `page.tsx`: Server Component, título "MEPIA — CONFIGURACIÓN INICIAL"
  - `OnboardingForm`: `"use client"`, estado de paso activo (1–4)
  - Indicador de progreso: 4 nodos con paso activo resaltado
  - Botón "Siguiente →" en pasos 1–3; "Guardar configuración ✓" solo en paso 4
  - Botón "← Anterior" visible desde paso 2
  - _Requirements: design_wireframes_onboarding.md, requirements.md §9_

- [x] 6. Crear `components/onboarding/BrandIdentityStep.tsx`
  - Textarea `brand_voice` (max 500 chars) con contador
  - Input de tags para `prohibited_recommendations` (agregar/eliminar)
  - Radio group `priority_focus`: efficiency | quality | growth
  - Validación inline: `brand_voice` requerido
  - _Requirements: design_wireframes_onboarding.md, _glossary.md OnboardingIdentityPayload_

- [x] 7. Crear `components/onboarding/AuditTolerancesStep.tsx`
  - Inputs numéricos: `max_cash_discrepancy_pct`, `max_cash_discrepancy_abs`
  - Inputs: `margin_warning_threshold`, `margin_critical_threshold`, `cost_spike_threshold_pct`
  - Validación: `margin_critical` < `margin_warning` (error inline si se viola)
  - _Requirements: design_wireframes_onboarding.md, _glossary.md OnboardingIdentityPayload_

- [x] 8. Crear `components/onboarding/CostStructureStep.tsx`
  - Tabla editable con columnas: Concepto, Monto/mes, Tolerancia, Tipo
  - Tipo: select `FIXED | VARIABLE | CAPEX`
  - Botón "+ Agregar costo", botón eliminar por fila
  - Mínimo 1 fila requerida (validación al intentar avanzar)
  - _Requirements: design_wireframes_onboarding.md, _glossary.md OnboardingIdentityPayload_

- [x] 9. Crear `components/onboarding/AuditRulesStep.tsx`
  - Input de tags para `red_alert_triggers` (agregar/eliminar)
  - Input de tags para `ignored_anomaly_types`
  - Radio group `audit_frequency`: daily | weekly
  - _Requirements: design_wireframes_onboarding.md, _glossary.md OnboardingIdentityPayload_

- [x] 10. Conectar `OnboardingForm` al API: POST/PUT onboarding
  - Al guardar en paso 4: `POST /api/onboarding` con `OnboardingIdentityPayload`
  - Si respuesta 409: reintentar con `PUT /api/onboarding`
  - Éxito → `router.push("/upload")`
  - Error 422 → mostrar mensaje inline en el campo inválido
  - _Requirements: design_flows.md §onboarding, requirements.md §9_

- [x] 11. Checkpoint — Verificar compilación de Fase 1
  - Ejecutar `next build` sin errores de TypeScript ni Tailwind
  - Verificar que `/onboarding` renderiza los 4 pasos con navegación funcional
  - Verificar que los badges de arquetipo y alert_level aplican los tokens correctos
  - Asegurar que no hay imports rotos en `AuditTable.tsx` tras refactor de badge
