"use client";

import { useState } from "react";

interface ReviewAlertProps {
  documentType: "pos" | "factura";
  fileId: string;
  missingFields: string[];
  onReviewed: () => void;
}

export default function ReviewAlert({
  documentType,
  fileId,
  missingFields,
  onReviewed,
}: ReviewAlertProps) {
  const [fieldValues, setFieldValues] = useState<Record<string, string>>(
    () => Object.fromEntries(missingFields.map((field) => [field, ""]))
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleFieldChange(field: string, value: string) {
    setFieldValues((prev) => ({ ...prev, [field]: value }));
  }

  async function handleConfirm() {
    setIsSubmitting(true);
    setError(null);

    try {
      const res = await fetch("/api/upload/review", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          file_id: fileId,
          document_type: documentType,
          field_corrections: fieldValues,
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(
          (data as { detail?: string }).detail ??
            `Error ${res.status}: no se pudo confirmar la revisión`
        );
      }

      onReviewed();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Error inesperado al confirmar"
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div
      className="bg-amber-950/30 border border-amber-700 rounded p-4 space-y-4"
      role="alert"
    >
      {/* Header */}
      <div>
        <h3 className="text-amber-400 text-sm font-semibold font-mono uppercase tracking-widest">
          ⚠ Revisión requerida
        </h3>
        <p className="mt-1 text-xs text-zinc-400">
          Los siguientes campos requieren revisión manual:
        </p>
      </div>

      {/* Editable field list */}
      <ul className="space-y-3">
        {missingFields.map((field) => (
          <li key={field} className="flex flex-col gap-1">
            <label
              htmlFor={`review-field-${field}`}
              className="text-label uppercase tracking-widest text-amber-400 font-mono"
            >
              {field}
            </label>
            <input
              id={`review-field-${field}`}
              type="text"
              value={fieldValues[field] ?? ""}
              onChange={(e) => handleFieldChange(field, e.target.value)}
              disabled={isSubmitting}
              placeholder={`Valor para ${field}`}
              className="bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-amber-600 disabled:opacity-50 font-mono"
            />
          </li>
        ))}
      </ul>

      {/* Inline error */}
      {error && (
        <p className="text-xs text-red-400" role="alert">
          {error}
        </p>
      )}

      {/* Confirm button */}
      <button
        type="button"
        onClick={handleConfirm}
        disabled={isSubmitting}
        className="w-full border border-amber-700 bg-amber-950/50 text-amber-400 text-label uppercase tracking-widest font-mono px-4 py-2 rounded-sm hover:bg-amber-950 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isSubmitting ? "Enviando..." : "Confirmar revisión"}
      </button>
    </div>
  );
}
