# Diseño Frontend — Design System (Tailwind)

**Referenciado desde:** `design.md`

## Propuesta de `tailwind.config.ts`

```typescript
import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Base — brutalismo oscuro
        canvas:   "#0f0f11",   // fondo raíz (más oscuro que zinc-900)
        surface:  "#18181b",   // zinc-900 — superficies primarias
        elevated: "#27272a",   // zinc-800 — tarjetas, paneles
        border:   "#3f3f46",   // zinc-700 — bordes visibles
        muted:    "#71717a",   // zinc-500 — texto secundario

        // Acento principal
        accent: {
          DEFAULT: "#34d399",  // emerald-400
          dim:     "#065f46",  // emerald-900 — fondos de badge
        },

        // Semáforo forense
        critical: {
          DEFAULT: "#ef4444",  // red-500
          bg:      "#450a0a",  // red-950
          border:  "#b91c1c",  // red-700
        },
        warning: {
          DEFAULT: "#f59e0b",  // amber-500
          bg:      "#451a03",  // amber-950
          border:  "#b45309",  // amber-700
        },
        info: {
          DEFAULT: "#71717a",  // zinc-500
          bg:      "#27272a",  // zinc-800
        },

        // Arquetipos CEO
        archetype: {
          operative: { badge: "#065f46", text: "#6ee7b7" }, // emerald
          purist:    { badge: "#2e1065", text: "#c4b5fd" }, // violet
          hacker:    { badge: "#451a03", text: "#fcd34d" }, // amber
        },
      },

      fontFamily: {
        sans:  ["Inter", "sans-serif"],
        mono:  ["JetBrains Mono", "Fira Code", "monospace"],
      },

      fontSize: {
        // Escala brutalista — pocos tamaños, contraste máximo
        "forensic-xl": ["2.25rem", { lineHeight: "1", fontWeight: "700", letterSpacing: "-0.02em" }],
        "forensic-lg": ["1.5rem",  { lineHeight: "1.2", fontWeight: "600" }],
        "label":       ["0.6875rem", { lineHeight: "1", fontWeight: "500", letterSpacing: "0.1em" }],
      },

      spacing: {
        "panel": "1.5rem",   // padding estándar de paneles
        "row":   "1.25rem",  // padding vertical de filas de tabla
      },

      borderWidth: {
        "alert": "2px",  // borde izquierdo de filas críticas
      },

      boxShadow: {
        "panel": "0 0 0 1px #3f3f46",  // borde sutil sin elevación
        "glow-critical": "0 0 12px 0 rgba(239,68,68,0.25)",
      },
    },
  },
  plugins: [],
};

export default config;
```

## Tokens de tipografía

| Uso | Clase | Fuente |
|-----|-------|--------|
| Títulos de sección | `text-forensic-lg font-semibold text-zinc-100` | Inter |
| Labels de columna | `text-label uppercase tracking-widest text-zinc-400` | Inter |
| Números forenses | `font-mono text-forensic-xl text-zinc-100` | JetBrains Mono |
| Texto de insight | `text-sm leading-relaxed text-zinc-200` | Inter |
| Texto muted | `text-xs text-zinc-500` | Inter |

## Tokens de badge por `alert_level`

```typescript
const alertBadge = {
  critical: "bg-red-950  text-red-400  border border-red-700",
  warning:  "bg-amber-950 text-amber-400 border border-amber-700",
  info:     "bg-zinc-800 text-zinc-400  border border-zinc-700",
}
```

## Tokens de badge por `archetype`

```typescript
const archetypeBadge = {
  "Operative Genius": "bg-emerald-900 text-emerald-300",
  "Product Purist":   "bg-violet-900  text-violet-300",
  "Growth Hacker":    "bg-amber-900   text-amber-300",
}
```

## Reglas brutalistas

- **Sin `rounded-full`** en elementos de datos — solo en badges de texto pequeño
- **Sin sombras de elevación** — usar `ring` o `border` para separar superficies
- **Números siempre en `font-mono`** — `quantified_impact`, totales, porcentajes
- **Bordes visibles** — `border border-zinc-800` en todas las tarjetas y tablas
- **Fila crítica** — `border-l-2 border-red-500 bg-red-950/20`

## Archivos relacionados de este nodo

- `design_components.md` — qué componentes usan estos tokens
- `design_wireframes.md` — cómo se aplica el sistema visual en el layout
