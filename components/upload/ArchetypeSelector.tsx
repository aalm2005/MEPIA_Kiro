"use client";

import ArchetypeBadge from "../ui/ArchetypeBadge";
import type { Archetype } from "../AuditTable";

interface ArchetypeSelectorProps {
  value: Archetype;
  onChange: (archetype: Archetype) => void;
}

const archetypes: { name: Archetype; description: string }[] = [
  {
    name: "Operative Genius",
    description: "Eficiencia operativa y procesos",
  },
  {
    name: "Product Purist",
    description: "Calidad del producto y experiencia",
  },
  {
    name: "Growth Hacker",
    description: "Escala, métricas y crecimiento",
  },
];

export default function ArchetypeSelector({
  value,
  onChange,
}: ArchetypeSelectorProps) {
  return (
    <div className="flex gap-3">
      {archetypes.map((archetype) => {
        const isActive = value === archetype.name;
        return (
          <button
            key={archetype.name}
            type="button"
            onClick={() => onChange(archetype.name)}
            className={`flex-1 border rounded p-4 cursor-pointer transition-all text-left ${
              isActive
                ? "border-emerald-500 bg-zinc-800"
                : "border-zinc-700 opacity-60"
            }`}
          >
            <ArchetypeBadge archetype={archetype.name} />
            <p className="mt-2 text-sm text-zinc-300">{archetype.description}</p>
          </button>
        );
      })}
    </div>
  );
}
