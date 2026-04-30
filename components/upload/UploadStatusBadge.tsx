export type UploadStatus =
  | "idle"
  | "uploading"
  | "done"
  | "error"
  | "needs_human_review";

interface UploadStatusBadgeProps {
  status: UploadStatus;
}

const badgeConfig: Record<
  Exclude<UploadStatus, "idle">,
  { classes: string; label: string }
> = {
  uploading: {
    classes: "bg-zinc-800 text-zinc-400 border border-zinc-700",
    label: "Procesando...",
  },
  done: {
    classes: "bg-accent-dim text-accent border border-accent",
    label: "Cargado ✓",
  },
  error: {
    classes: "bg-red-950 text-red-400 border border-red-700",
    label: "Error",
  },
  needs_human_review: {
    classes: "bg-amber-950 text-amber-400 border border-amber-700",
    label: "Revisión requerida",
  },
};

export default function UploadStatusBadge({ status }: UploadStatusBadgeProps) {
  if (status === "idle") return null;

  const { classes, label } = badgeConfig[status];

  return (
    <span
      className={`inline-flex items-center gap-1.5 text-label uppercase tracking-widest px-2 py-0.5 rounded-sm font-mono ${classes}`}
    >
      {label}
    </span>
  );
}
