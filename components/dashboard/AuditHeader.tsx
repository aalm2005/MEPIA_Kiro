interface AuditHeaderProps {
  riskLevel: "low" | "medium" | "high";
  date?: string;
}

const riskBadgeConfig = {
  high: {
    className: "bg-red-950 text-red-400 border border-red-700",
    label: "RIESGO ALTO",
  },
  medium: {
    className: "bg-amber-950 text-amber-400 border border-amber-700",
    label: "RIESGO MEDIO",
  },
  low: {
    className: "bg-zinc-800 text-zinc-400 border border-zinc-700",
    label: "RIESGO BAJO",
  },
} as const;

export function AuditHeader({ riskLevel, date }: AuditHeaderProps) {
  const badge = riskBadgeConfig[riskLevel];

  return (
    <>
      {riskLevel === "high" && (
        <div className="fixed top-0 left-0 right-0 z-50 bg-red-950 border-b border-red-700 text-red-400 text-xs text-center py-1.5 font-mono uppercase tracking-widest">
          ⚠ Nivel de riesgo crítico detectado — revisión inmediata requerida
        </div>
      )}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-forensic-lg font-semibold text-zinc-100 uppercase tracking-widest">
            MEPIA — Reporte de Auditoría Forense
          </h1>
          {date && (
            <p className="text-xs text-zinc-500 font-mono mt-0.5">{date}</p>
          )}
        </div>
        <span
          className={`text-label uppercase tracking-widest px-2 py-0.5 rounded-sm font-mono ${badge.className}`}
        >
          {badge.label}
        </span>
      </div>
    </>
  );
}
