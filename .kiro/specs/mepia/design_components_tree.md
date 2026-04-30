# Diseño Frontend — Árbol Completo de Componentes

**Referenciado desde:** `design_components.md`

## Árbol por ruta

```
app/
├── layout.tsx                    # RootLayout — fuente, bg-zinc-900, antialiased
│
├── onboarding/
│   └── page.tsx                  # OnboardingPage (Server Component)
│       └── OnboardingForm        # "use client" — 4 pasos
│           ├── BrandIdentityStep # brand_voice, prohibited_recommendations, priority_focus
│           ├── AuditTolerancesStep # discrepancia, margen warning/crítico, spike
│           ├── CostStructureStep # lista ExpectedCostStructure (add/remove)
│           └── AuditRulesStep    # red_alert_triggers, ignored_anomaly_types
│
├── upload/
│   └── page.tsx                  # UploadPage (Server Component)
│       └── UploadForm            # "use client"
│           ├── OnboardingGate    # Verifica onboarding_complete antes de mostrar form
│           ├── ArchetypeSelector # 3 tarjetas: Operative | Purist | Hacker
│           ├── DocumentDropzone  # POS — drag & drop + click, acepta .pdf
│           ├── DocumentDropzone  # Factura — drag & drop + click, acepta .pdf,.xml
│           ├── UploadStatusBadge # idle | uploading | done | error
│           └── ReviewAlert       # Visible si needs_human_review: true
│
└── dashboard/
    └── page.tsx                  # DashboardPage (Server Component)
        ├── AuditHeader           # Título + risk_level badge global
        ├── PipelineStatusBar     # S1→S2→S3→S4→N05 [→L2 si escalated]
        ├── Layer2Banner          # Solo si pipeline_status: "escalated"
        ├── AuditTable            # Tabla forense principal
        │   ├── AuditRow          # módulo | raw_result | copilot_phrase | alert_level
        │   └── ArchetypeBadge    # Badge por arquetipo CEO
        ├── ForensicSummary       # Panel lateral 35%
        │   └── AnomalyCard       # quantified_impact + severity + data_points
        └── DormantMetricsList    # Métricas sin datos suficientes
```

## Contratos de props clave

### `AuditTable`
```typescript
interface AuditTableProps {
  rows: AuditInsight[] | AuditRow[]
  isLoading?: boolean
  emptyMessage?: string
}
```

Columnas: Módulo (15%) · Resultado Forense (30%) · Insight CEO (35%) · Nivel (10%) · Acción (10%)

Fila `critical`: `border-l-2 border-red-500 bg-red-950/20`

## Archivos relacionados de este nodo

- `design_components.md` — especificación de componentes nuevos
- `design_wireframes.md` — posición en el layout
