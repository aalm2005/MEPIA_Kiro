import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas:   "#0f0f11",
        surface:  "#18181b",
        elevated: "#27272a",
        border:   "#3f3f46",
        muted:    "#71717a",
        accent: {
          DEFAULT: "#34d399",
          dim:     "#065f46",
        },
        critical: {
          DEFAULT: "#ef4444",
          bg:      "#450a0a",
          border:  "#b91c1c",
        },
        warning: {
          DEFAULT: "#f59e0b",
          bg:      "#451a03",
          border:  "#b45309",
        },
        info: {
          DEFAULT: "#71717a",
          bg:      "#27272a",
        },
        archetype: {
          operative: { badge: "#065f46", text: "#6ee7b7" },
          purist:    { badge: "#2e1065", text: "#c4b5fd" },
          hacker:    { badge: "#451a03", text: "#fcd34d" },
        },
      },
      fontFamily: {
        sans:  ["Inter", "sans-serif"],
        mono:  ["JetBrains Mono", "Fira Code", "monospace"],
      },
      fontSize: {
        "forensic-xl": ["2.25rem", { lineHeight: "1", fontWeight: "700", letterSpacing: "-0.02em" }],
        "forensic-lg": ["1.5rem",  { lineHeight: "1.2", fontWeight: "600" }],
        "label":       ["0.6875rem", { lineHeight: "1", fontWeight: "500", letterSpacing: "0.1em" }],
      },
      spacing: {
        "panel": "1.5rem",
        "row":   "1.25rem",
      },
      borderWidth: {
        "alert": "2px",
      },
      boxShadow: {
        "panel": "0 0 0 1px #3f3f46",
        "glow-critical": "0 0 12px 0 rgba(239,68,68,0.25)",
      },
    },
  },
  plugins: [],
};

export default config;
