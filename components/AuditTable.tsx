export type Archetype = "Operative Genius" | "Product Purist" | "Growth Hacker";

export interface AuditRow {
  module: string;
  raw_result: string;
  copilot_phrase: string;
  archetype: Archetype;
}

interface Props {
  rows: AuditRow[];
}

const archetypeBadge: Record<Archetype, string> = {
  "Operative Genius": "bg-emerald-900 text-emerald-300",
  "Product Purist":   "bg-violet-900 text-violet-300",
  "Growth Hacker":    "bg-amber-900 text-amber-300",
};

export default function AuditTable({ rows }: Props) {
  return (
    <div className="w-full overflow-x-auto rounded-xl border border-zinc-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-800 text-zinc-400 text-left">
            <th className="px-6 py-4 font-medium w-1/5">Módulo</th>
            <th className="px-6 py-4 font-medium w-2/5">Resultado del Agente</th>
            <th className="px-6 py-4 font-medium w-2/5">Insight del Copiloto</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={i}
              className="border-b border-zinc-800 last:border-0 hover:bg-zinc-800/40 transition-colors"
            >
              {/* Módulo */}
              <td className="px-6 py-5 font-semibold text-zinc-100 align-top">
                {row.module}
              </td>

              {/* Resultado crudo del agente */}
              <td className="px-6 py-5 text-zinc-300 align-top">
                {row.raw_result}
              </td>

              {/* Frase del Copiloto + arquetipo */}
              <td className="px-6 py-5 align-top">
                <span
                  className={`inline-block text-xs px-2 py-0.5 rounded-full mb-2 font-medium ${archetypeBadge[row.archetype]}`}
                >
                  {row.archetype}
                </span>
                <p className="text-zinc-200 leading-relaxed">
                  &ldquo;{row.copilot_phrase}&rdquo;
                </p>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
