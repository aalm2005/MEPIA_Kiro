export type AlertLevel = "critical" | "warning" | "info";

export const alertBadge: Record<AlertLevel, string> = {
  critical: "bg-red-950  text-red-400  border border-red-700",
  warning:  "bg-amber-950 text-amber-400 border border-amber-700",
  info:     "bg-zinc-800 text-zinc-400  border border-zinc-700",
};

interface Props {
  level: AlertLevel;
}

export default function AlertLevelBadge({ level }: Props) {
  return (
    <span
      className={`inline-block text-label uppercase tracking-widest px-2 py-0.5 rounded-sm font-mono ${alertBadge[level]}`}
    >
      {level}
    </span>
  );
}
