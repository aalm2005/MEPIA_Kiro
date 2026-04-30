# Diseño Frontend — Árbol de Componentes

**Referenciado desde:** `design.md`
**Árbol completo:** `design_components_tree.md`

## Componentes nuevos (v1.1)

### `ArchetypeSelector.tsx`

```typescript
type Archetype = "Operative Genius" | "Product Purist" | "Growth Hacker"
interface ArchetypeSelectorProps {
  value: Archetype
  onChange: (archetype: Archetype) => void
}
```

3 tarjetas seleccionables. Activa: `border-emerald-500 bg-zinc-800`.
Inactivas: `border-zinc-700 opacity-60`. Default: `"Operative Genius"`.

### `OnboardingGate.tsx`

Server Component. Llama `GET /business/{id}/onboarding/status`.
`onboarding_complete: false` → `OnboardingRequiredBanner` con link a `/onboarding`.
`onboarding_complete: true` → renderiza `children`.

### `Layer2Banner.tsx`

Banner ámbar colapsable. Solo visible cuando `pipeline_status: "escalated"`.
`running` → spinner · `completed` → "Ver análisis profundo →" · `failed` → error.

### `PipelineStatusBar.tsx` (extendido)

```typescript
interface PipelineStatusBarProps {
  status: "idle"|"running"|"completed"|"partial"|"escalated"|"failed"
  currentNode?: string
  layer2Status?: "running"|"completed"|"failed"
}
```

Pasos: S1 → S2 → S3 → S4 → N05. Si `escalated`, agrega nodo `[L2]` al final.

### `OnboardingForm.tsx` (nuevo)

4 pasos lineales: `BrandIdentityStep` → `AuditTolerancesStep` →
`CostStructureStep` → `AuditRulesStep`. Botón "Guardar" solo en paso 4.

## Componentes existentes (sin cambios de interfaz)

- `AuditTable` — se extiende con columna `alert_level` y `recommended_action`
- `AnomalyCard` — `quantified_impact` en `font-mono text-2xl`
- `DocumentDropzone` — valida MIME antes de enviar

Ver `design_components_tree.md` para el árbol completo con todas las rutas.

## Archivos relacionados de este nodo

- `design_components_tree.md` — árbol completo de componentes por ruta
- `design_system.md` — tokens de color para badges y bordes
- `design_wireframes.md` — posición de cada componente en el layout
