# Diseño Frontend — Árbol de Componentes

**Referenciado desde:** `design.md`

## Árbol de componentes

```
app/
├── layout.tsx                    # RootLayout — fuente, bg-zinc-900, antialiased
├── upload/
│   └── page.tsx                  # UploadPage (Server Component wrapper)
│       └── UploadForm            # "use client" — maneja estado de ingesta
│           ├── DocumentDropzone  # Drag & drop + file input (POS o factura)
│           ├── UploadStatusBadge # idle | uploading | done | error
│           └── ReviewAlert       # Aparece si needs_human_review: true
└── dashboard/
    └── page.tsx                  # DashboardPage (Server Component)
        ├── AuditHeader           # Título + risk_level badge global
        ├── PipelineStatusBar     # Barra de progreso del pipeline (S1→N05)
        ├── AuditTable            # Tabla forense principal (extendida)
        │   ├── AuditRow          # Fila: módulo | raw_result | insight CEO
        │   └── ArchetypeBadge    # Badge de color por arquetipo
        ├── ForensicSummary       # Panel lateral: anomalías críticas destacadas
        │   └── AnomalyCard       # Tarjeta por AnomalyItem de severidad high/medium
        └── DormantMetricsList    # Métricas dormant: qué datos faltan
```

## Especificación de componentes clave

### `AuditTable.tsx` (extendido)

Maneja dos fuentes de datos:
- `AuditInsight[]` — output de N05 (modo producción)
- `AuditRow[]` — mock / agentes paralelos (modo desarrollo)

```typescript
interface AuditTableProps {
  rows: AuditInsight[] | AuditRow[]
  isLoading?: boolean
  emptyMessage?: string
}
```

Columnas:
| Col | Fuente | Ancho |
|-----|--------|-------|
| Módulo | `module` | 15% |
| Resultado Forense | `raw_result` | 30% |
| Insight CEO | `copilot_phrase` + `archetype` badge | 35% |
| Nivel | `alert_level` badge | 10% |
| Acción | `recommended_action` (colapsable) | 10% |

La columna **Nivel** es nueva: badge `critical` (rojo), `warning` (ámbar), `info` (zinc).
Filas con `alert_level: "critical"` tienen borde izquierdo `border-l-2 border-red-500`.

### `AnomalyCard.tsx`

```typescript
interface AnomalyCardProps {
  anomaly: AnomalyItem
  archetype: Archetype
}
```

Muestra: tipo de anomalía, `quantified_impact` en tipografía monoespaciada grande,
`severity` badge, y `data_points` en lista colapsable.

### `DocumentDropzone.tsx`

```typescript
interface DocumentDropzoneProps {
  documentType: "pos" | "factura"
  onFileSelected: (file: File) => void
  accept: string  // ".pdf" | ".pdf,.xml"
}
```

Acepta drag & drop y click. Muestra nombre del archivo seleccionado y tamaño.
Valida MIME antes de enviar (no solo extensión).

### `PipelineStatusBar.tsx`

```typescript
interface PipelineStatusBarProps {
  status: "idle" | "running" | "completed" | "partial" | "failed"
  currentNode?: string  // ej. "S4_forensic_cfo"
}
```

Barra horizontal con nodos del pipeline como pasos: S1 → S2 → S3 → S4 → N05.
Cada nodo se ilumina en `emerald-400` al completarse.

## Archivos relacionados de este nodo

- `design_system.md` — tokens de color para badges y bordes de alerta
- `design_wireframes.md` — posición de cada componente en el layout
