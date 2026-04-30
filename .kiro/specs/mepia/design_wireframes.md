# Diseño Frontend — Wireframing Lógico

**Referenciado desde:** `design.md`

## Layout `/app/dashboard`

```
┌─────────────────────────────────────────────────────────────┐
│ MEPIA                              [risk_level: HIGH ●]     │  ← AuditHeader
│ Reporte de Auditoría Forense       Última auditoría: hoy    │
├─────────────────────────────────────────────────────────────┤
│ Pipeline: [S1 ✓]──[S2 ✓]──[S3 ✓]──[S4 ✓]──[N05 ✓]        │  ← PipelineStatusBar
├──────────────────────────────────┬──────────────────────────┤
│                                  │  ANOMALÍAS CRÍTICAS      │
│  TABLA FORENSE PRINCIPAL         │  ┌────────────────────┐  │
│  ┌──────┬──────────┬──────────┐  │  │ margin_leak        │  │
│  │Módulo│Resultado │Insight   │  │  │ -10% margen        │  │
│  │      │Forense   │CEO       │  │  │ ~$1,200 MXN        │  │
│  ├──────┼──────────┼──────────┤  │  └────────────────────┘  │
│  │ ●    │ raw_res  │ frase +  │  │  ┌────────────────────┐  │
│  │ crit │ número   │ badge    │  │  │ source_discrepancy │  │
│  ├──────┼──────────┼──────────┤  │  │ -320 MXN           │  │
│  │ ▲    │ raw_res  │ frase +  │  │  └────────────────────┘  │
│  │ warn │ número   │ badge    │  │                          │
│  ├──────┼──────────┼──────────┤  │  MÉTRICAS DORMANT        │
│  │ ─    │ raw_res  │ frase +  │  │  · inventory_variance    │
│  │ info │ número   │ badge    │  │    falta: recipes        │
│  └──────┴──────────┴──────────┘  │                          │
│                                  │                          │
└──────────────────────────────────┴──────────────────────────┘
```

**Proporciones:** tabla principal 65% · panel lateral 35%

### Jerarquía visual del dashboard

1. **Banner `risk_level: "high"`** — barra roja en la parte superior, imposible ignorar
2. **Filas `critical`** — borde izquierdo rojo + fondo `red-950/20`, flotan visualmente
3. **`AnomalyCard`** en panel lateral — `quantified_impact` en `font-mono text-2xl`
4. **Filas `warning`** — borde ámbar, sin fondo especial
5. **Filas `info`** — estilo base, sin énfasis

### Comportamiento del panel lateral

- Si `risk_level: "low"` → panel lateral muestra solo métricas dormant (sin anomaly cards)
- Si `risk_level: "medium"` → muestra anomalías `warning` en panel
- Si `risk_level: "high"` → muestra anomalías `critical` primero, luego `warning`

---

## Layout `/app/upload`

```
┌─────────────────────────────────────────────────────────────┐
│ INGESTA                                                     │
│ Subir Documentos de Auditoría                               │
├──────────────────────────┬──────────────────────────────────┤
│  TICKET POS              │  FACTURA DE PROVEEDOR            │
│  ┌────────────────────┐  │  ┌────────────────────────────┐  │
│  │                    │  │  │                            │  │
│  │  Arrastra tu PDF   │  │  │  Arrastra PDF o XML        │  │
│  │  de ventas aquí    │  │  │  de factura aquí           │  │
│  │                    │  │  │                            │  │
│  │  [Seleccionar PDF] │  │  │  [Seleccionar archivo]     │  │
│  └────────────────────┘  │  └────────────────────────────┘  │
│                          │                                  │
│  Estado: idle            │  Estado: idle                    │
├──────────────────────────┴──────────────────────────────────┤
│  [Analizar con Agentes IA →]                                │
│                                                             │
│  ⚠ needs_human_review: true → ReviewAlert aparece aquí     │
└─────────────────────────────────────────────────────────────┘
```

### Estados del formulario de upload

| Estado | Visual |
|--------|--------|
| `idle` | Dropzone con borde `border-dashed border-zinc-700` |
| `uploading` | Spinner + texto "Procesando OCR..." |
| `done` | Borde `border-emerald-500` + checkmark |
| `error` | Borde `border-red-500` + mensaje de error |
| `needs_human_review` | `ReviewAlert` con campos faltantes listados |

## Archivos relacionados de este nodo

- `design_components.md` — especificación de cada componente del wireframe
- `design_flows.md` — lógica de transición entre estados
