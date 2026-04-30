import type { Archetype } from "../AuditTable";

export const archetypeBadge: Record<Archetype, string> = {
  "Operative Genius": "bg-emerald-900 text-emerald-300",
  "Product Purist":   "bg-violet-900  text-violet-300",
  "Growth Hacker":    "bg-amber-900   text-amber-300",
};

interface Props {
  archetype: Archetype;
}

export default function ArchetypeBadge({ archetype }: Props) {
  return (
    <span
      className={`inline-block text-label uppercase tracking-widest px-2 py-0.5 rounded-sm font-mono ${archetypeBadge[archetype]}`}
    >
      {archetype}
    </span>
  );
}
